import traceback
import netrc
import logging
import glob
import re
import jinja2
import json
import urllib
import os
import posixpath
import functools
import collections
import typing
import dataclasses
import requests
import html
import sys
import bs4
import subprocess
import tweepy  # type: ignore[import]
import timeout_decorator  # type: ignore[import]

import markdown
import xml.etree.ElementTree as ET
import gallery_dl  # type: ignore[import]
from pelican import signals  # type: ignore[import]

import chitose  # type: ignore[import]

env = jinja2.Environment(undefined=jinja2.StrictUndefined)
envUnstrict = jinja2.Environment()

logging.basicConfig(level=logging.WARNING)

def summarize_html(html_code):
    # logging.warning(html_code)
    soup = bs4.BeautifulSoup(html_code, features="lxml")
    return soup.text


env.filters['summarize_html'] = summarize_html
envUnstrict.filters['summarize_html'] = summarize_html

def urlretrieve(src: str, dest: str) -> None:
    try:
        urllib_request = urllib.request   # type: ignore[attr-defined]
        opener = urllib_request.build_opener()
        opener.addheaders = [('User-agent', 'curl/8.0.1')]
        urllib_request.install_opener(opener)
        urllib_request.urlretrieve(src, dest)
        # resp = requests.get(src, headers={'User-Agent': 'curl/8.0.1'})

    except Exception as e:
        try:
            return urllib_request.urlretrieve('https://web.archive.org/web/0im_/' + src, dest)  # type: ignore[return-value]
        except:
            raise e


@dataclasses.dataclass(unsafe_hash=True)
class PostReference():
    user_id: str = dataclasses.field(hash=True)
    post_id: str = dataclasses.field(hash=True)

# @dataclasses.dataclass()
# class WorkResult():
#     result: typing.Any
#     nontrivial: bool


WorkResult = collections.namedtuple("WorkResult", ["result", "nontrivial"])


class PermaSocial:
    NOUN_POST = "post"
    LINK_RE = r"/(?P<user_id>[^/]+)/post/(?P<post_id>[^ )]+)"

    EMBED_TEMPLATE = env.from_string(
        """{{ user.name }}: {{ text|replace("\n\n", " - ")|replace("\n", " - ") }}]"""
        """(/{{ user.id }}/post/{{ post_id }}"""  # )
    )
    POST_HTML_TEMPLATE = env.from_string(
        """<pre>{{ author.handle }}: {{ record.text|replace("\n\n", " - ")|replace("\n", " - ") }}]"""
        """(https://bsky.app/profile/{{ author.handle }}/post/{{ url_id }}</pre>"""  # )
    )

    SET_ALWAYS_RECURSE = False

    @dataclasses.dataclass(unsafe_hash=True)
    class PostRef(PostReference):
        pass

    def __init__(self):
        self._api = None
        self.EMBED_NOTITLE_RE = r"(?<=\!\[\]\()" + self.LINK_RE + r"(?=\))"

    @property
    def api(self):
        if self._api is None:
            # traceback.print_stack()
            self.login()

        return self._api

    def login(self):
        raise NotImplementedError

    def getRelatedPosts(self, post_json: dict, post_reference: PostReference) -> typing.Iterable[PostReference]:
        raise NotImplementedError

    @classmethod
    def getPostFilePath(cls, json_obj, post_reference: PostReference, makedirs=True, media_id=None):
        # json_obj is unused
        dest_dir = os.path.join(f"{cls.NOUN_POST}s", post_reference.user_id)

        if makedirs:
            os.makedirs(dest_dir, exist_ok=True)

        filename = f"s{post_reference.post_id}.json"
        if media_id:
            filename = f"s{post_reference.post_id}-{media_id}"

        return os.path.join(dest_dir, filename)

    def seasonPostReference(self, json_obj, post_reference: PostReference) -> None:
        # Use json_obj to populate post_reference with any additional useful info
        pass

    def getPostJson(self, post_reference: PostReference, get_media=True, reason="Unknown", _traversed=[]):
        # logging.debug(f"Starting lookup of {post_reference} for {reason}")

        last_exception: Exception = NotImplemented
        for getter in self.JSON_GETTERS:
            try:
                (json_obj, did_new_work) = getter(self, post_reference, reason=reason)
                # = (getter.__name__ != self.getPostJsonCached.__name__)

                self.seasonPostReference(json_obj, post_reference)

                if self.SET_ALWAYS_RECURSE or did_new_work:
                    with open(self.getPostFilePath(json_obj, post_reference), "w") as fp:
                        json.dump(json_obj, fp, indent=2)

                    # First run resource gathering, but save this json_obj first.
                    if get_media:
                        self.savePostMedia(json_obj, post_reference)
                    for pr2 in self.getRelatedPosts(json_obj, post_reference):
                        if pr2 not in _traversed:
                            self.getPostJson(
                                pr2,
                                reason=f"related to {post_reference}",
                                _traversed=_traversed + [(post_reference)]
                            )
                return json_obj
            except Exception as e:
                last_exception = e
                logging.warning(
                    f"{getter.__name__!s} Failed to lookup {(post_reference)} for {reason}",
                    exc_info=False
                )
        raise last_exception

    def getPostJsonCached(self, post_reference, reason="Unknown") -> WorkResult:
        dest_path = self.getPostFilePath(dict(), post_reference)
        with open(dest_path, "r", encoding="utf-8", newline='\n') as fp:
            return WorkResult(json.load(fp), nontrivial=False)

    JSON_GETTERS: typing.List[typing.Callable] = [getPostJsonCached]

    def getRealSourceUrl(self, media_obj):
        raise NotImplementedError

    def getPostMedia(self: typing.Self, json_obj) -> typing.Iterable[typing.Tuple[str, typing.Union[str, typing.Callable]]]:
        logging.error(json_obj)
        raise NotImplementedError

    def savePostMedia(self, json_obj, post_reference: PostReference, reason="Unknown"):
        for (mname, src_url) in self.getPostMedia(json_obj):
            try:
                media_dest_path = self.getPostFilePath(json_obj, post_reference, media_id=mname)

                if isinstance(src_url, str):
                    if not os.path.isfile(media_dest_path):
                        logging.warning(f"DL {src_url} -> {media_dest_path}")
                        urlretrieve(src_url, media_dest_path)
                elif hasattr(src_url, '__call__'):
                    src_url(media_dest_path)
                else:
                    raise NotImplementedError(src_url)

            except Exception as e:
                logging.error(f"Media error {post_reference}: {e}")
                open(media_dest_path, 'wb')  # touch file

    def embedprocessor(superself, *args, **kwargs):

        class EmbedProcessor(markdown.inlinepatterns.LinkInlineProcessor):
            """ Return a link element from the given match. """

            def handleMatch(self, m, data) -> ET:
                title, index, handled = self.getText(data, m.end(0))
                if not handled:
                    return None, None, None

                href, matches, __, index, handled = self.getLink(data, index)
                if not handled:
                    return None, None, None

                post_reference: typing.Optional[PostReference] = None
                try:
                    post_reference = superself.PostRef(**matches)  # type: ignore[arg-type]
                    json_obj = superself.getPostJson(post_reference, get_media=True, reason=m)

                except Exception:
                    logging.error(f"Can't load {superself.NOUN_POST} " + repr(post_reference), exc_info=True)
                    return ET.fromstring(f"<p>ERROR! Can't load {superself.NOUN_POST} <a href='{href}'>'{title}'</a></p>"), m.start(0), index

                string = f"{data=}, {post_reference=}"  # For error case only
                extra_attrs = " ".join([
                    f'data-{k}="{v}"' for k, v in
                    dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(href).query)).items()  # type: ignore[type-var]
                ])
                try:
                    string = superself.POST_HTML_TEMPLATE.render(extra_attrs=extra_attrs, **matches, **json_obj)  # type: ignore[arg-type]
                    # return ET.fromstring(string), m.start(0), m.end(0)
                    return self.md.htmlStash.store(string), m.start(0), index
                except Exception as e:
                    logging.error(string, exc_info=True)
                    raise e

            def getLink(self, data, index) -> typing.Union[typing.Tuple[str, typing.Mapping[str, str], str, str, bool], typing.Tuple[None, None, None, None, None]]:
                href, title, index, handled = super().getLink(data, index)
                if handled:
                    # logging.debug(("saw", href, title, index, handled))
                    # It's an image, but is it a post?
                    match = re.match(superself.LINK_RE, href)
                    if match:
                        # logging.debug(("matched", href, title, index, handled))
                        return href, match.groupdict(), title, index, handled
                return None, None, None, None, None

        return EmbedProcessor(*args, **kwargs)

    def replaceBlanksInFile(self, filepath, replace_only_uncaptioned=True):
        with open(filepath, "r", encoding="utf-8") as fp:
            body = fp.read()

        dirty = False
        match_pattern = self.EMBED_NOTITLE_RE if replace_only_uncaptioned else self.LINK_RE
        for match in re.finditer(match_pattern, body):
            force_uncaptioned_prefix = "![" if replace_only_uncaptioned else ""
            # try:
            matches = match.groupdict()
            post_reference = self.PostRef(**matches)
            json_obj = self.getPostJson(post_reference, get_media=True, reason=matches)

            try:
                rendered = force_uncaptioned_prefix + self.EMBED_TEMPLATE.render(**matches, **json_obj)
            except Exception as e:
                logging.error(matches, exc_info=False)
                logging.error(json_obj, exc_info=False)
                raise e
            whole_md_object = force_uncaptioned_prefix + "](" + match.group(0)

            logging.debug(f"{whole_md_object!r} -> {rendered!r}")
            body = body.replace(whole_md_object, rendered)
            dirty = True

        if dirty:
            with open(filepath, "w", encoding="utf-8", newline='\n') as fp:
                fp.write(body)


def bs_htmlize(text, facets):
    paragraphs = "<p>" + text.replace("\n\n", "</p><p>").replace("\n", "</p><p>") + "</p>"

    for facet in (facets or []):
        for feature in facet['features']:
            if feature['$type'] == "app.bsky.richtext.facet#link":
                paragraphs = paragraphs.replace(
                    feature['uri'],
                    f"<a href='{feature['uri']}'>{feature['uri']}</a>"
                )
            elif feature['$type'] == "app.bsky.richtext.facet#mention":
                continue
            else:
                raise NotImplementedError(feature['$type'])
    return paragraphs


env.filters['bs_htmlize'] = bs_htmlize
envUnstrict.filters['bs_htmlize'] = bs_htmlize

class PermaBluesky(PermaSocial):
    NOUN_POST = "skeet"
    LINK_RE = r"(https|http)://(www.){0,1}bsky.app/profile/(?P<user_id>[^/]+)/post/(?P<post_id>[^ )]+)"

    EMBED_TEMPLATE = env.from_string(
        """{{ author.handle }}: {{ record.text|replace("\n\n", " - ")|replace("\n", " - ") }}]"""
        """(https://bsky.app/profile/{{ author.handle }}/post/{{ post_id }}"""  # )
    )

    POST_HTML_TEMPLATE = envUnstrict.from_string(re.sub(r'\n +', '', """
<blockquote class="twitter-tweet" data-lang="en" data-dnt="true" data-nosnippet="true" {{ extra_attrs }}>
    <div class="header">
    {% autoescape true %}
        <a href="https://bsky.app/profile/{{ author.handle }}/">
            <img src="{{ author.avatar }}"
                onerror="(async () => {this.onerror=null;this.src=`https://web.archive.org/web/0/${this.src}`;})();"
            ></img>
            <div class="vertical">
                <span class="name">{{ author.displayName }}</span>
                <span class="at">@{{ author.handle }}</span>
            </div>
        </a>
    {% endautoescape %}
    </div>
    <div>
        {{ record.text|bs_htmlize(record.facets)|safe }}
    </div>
    {% if embed %}
    <div class="media" style="display: none;">
    {% for e in embed.images %}
    <a href="{{e.fullsize}}" target="_blank">
        <img class="img count{media_count}" src="{{e.fullsize}}"
             onerror="(async () => {this.onerror=null;this.src=`https://web.archive.org/web/0/${this.src}`;})();"
        ></img>
    </a>
    {% endfor %}
    </div>
    {% endif %}
    <a href="https://bsky.app/profile/{{ author.handle }}/post/{{ id }}" target="_blank">{{ record.createdAt }}</a>
</blockquote>"""))

    def login(self, instance="bsky.social"):
        try:
            rc = netrc.netrc()
            (BSKY_USER, _, BSKY_PASSWD) = rc.authenticators(instance)

            self._api = chitose.BskyAgent(service=f'https://{instance}')
            self._api.login(BSKY_USER, BSKY_PASSWD)
            logging.info(f"Logged into {instance} as {BSKY_USER}")
        except Exception:
            traceback.print_exc()
            logging.info(f"API not configured; using local {self.NOUN_POST}s only.")

    BSKY_CACHE: typing.Mapping[PostReference, typing.Any] = {}

    def getPostMedia(self, json_obj) -> typing.Iterable[typing.Tuple[str, str]]:
        for image_def in json_obj.get('embed', {}).get('images', []):
            src_url = image_def['fullsize']
            name = posixpath.split(src_url)[-1].replace('@', '.')
            yield (name, src_url)

    @functools.lru_cache()
    def bskyGetDid(self, user_id: str) -> str:
        # logging.debug(f"bskyGetDid cache miss {user_id}")
        return json.loads(self.api.get_profile(actor=user_id))['did']

    @functools.lru_cache()
    def bskyTupleToUri(self, post_reference: PostReference) -> str:
        if hit := self.bskyTupleToUri_cache.get(post_reference):
            # logging.debug(f"bskyTupleToUri cache HIT {post_reference}")
            return hit

        # logging.debug(f"bskyTupleToUri cache miss {post_reference}")
        # logging.debug(self.bskyTupleToUri_cache)
        return f"at://{self.bskyGetDid(post_reference.user_id)}/app.bsky.feed.post/{post_reference.post_id}"

    bskyTupleToUri_cache: typing.Dict[PostReference, str] = {}

    def bskyPostToRef(self, post: typing.Dict) -> PostReference:
        return self.PostRef(
            user_id=post['author']['handle'],
            post_id=posixpath.split(post['uri'])[-1]
        )

    def bskyEncachenPost(self, post: typing.Dict) -> None:
        if post:
            u2 = post['author']['handle']
            p2 = posixpath.split(post['uri'])[-1]
            self.bskyTupleToUri_cache[self.PostRef(user_id=u2, post_id=p2)] = post['uri']

    @functools.lru_cache()
    def bskyGetThread(self, post_reference: PostReference) -> dict:
        # logging.debug(f"bskyGetThread cache miss {(post_reference)}")
        thread_response = self.api.get_post_thread(uri=self.bskyTupleToUri(post_reference))
        thread_response = json.loads(thread_response)

        self.bskyEncachenPost(thread_response['thread']['post'])
        self.bskyEncachenPost(thread_response['thread'].get('parent', {}).get('post'))
        for reply in thread_response['thread'].get('replies', []):
            self.bskyEncachenPost(reply['post'])

        return thread_response

    def getSkeetJsonApi(self, post_reference: PostReference, reason=""):
        if self.BSKY_CACHE.get(post_reference):
            return WorkResult(result=self.BSKY_CACHE[post_reference], nontrivial=True)

        try:
            thread_response = self.bskyGetThread(post_reference)
            thread_response['thread']['post']['id'] = post_reference.post_id

            logging.info(f"Downloaded new {self.NOUN_POST} for {post_reference} ({reason})")
            # print(thread_response)
            json_obj = thread_response['thread']['post']

            self.BSKY_CACHE[post_reference] = json_obj

            for json_obj_ex in thread_response['thread']['replies']:
                pr2 = self.bskyPostToRef(json_obj_ex['post'])
                self.BSKY_CACHE[pr2] = json_obj_ex['post']
                self.BSKY_CACHE[pr2]['id'] = pr2.post_id

            return WorkResult(result=json_obj, nontrivial=True)

        except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
            logging.error(e.headers)
            logging.error(e.fp.read())
            raise e
        except Exception:
            raise

    def getRelatedPosts(self, post_json: dict, post_reference: PostReference) -> typing.Iterable[PostReference]:
        # return []
        ref = self.PostRef(
            user_id=post_json['author']['handle'],
            post_id=post_json['id']
        )
        thread_response = self.bskyGetThread(ref)
        if parent := thread_response['thread'].get('parent'):
            yield self.bskyPostToRef(parent['post'])

        for reply in thread_response['thread'].get('replies', []):
            yield self.bskyPostToRef(reply['post'])

    JSON_GETTERS = [*PermaSocial.JSON_GETTERS, getSkeetJsonApi]


class PermaMastodon(PermaSocial):
    NOUN_POST = "toot"
    LINK_RE = r"(https|http)://(?P<instance>[^/]+)/@(?P<user_id>[^/]+)/(?!statuses/)(?P<post_id>[^ )]+)"

    EMBED_TEMPLATE = env.from_string(
        """{{ account.username }}@{{ instance }}: {{ content|summarize_html|e|replace("\n\n", " - ")|replace("\n", " - ") }}]({{ url }}"""  # )
    )

    POST_HTML_TEMPLATE = env.from_string(re.sub(r'\n +', '', """<blockquote class="fediverse-toot" data-lang="en" data-dnt="true" data-nosnippet="true" {{ extra_attrs }}>
    <div class="header">
    {% autoescape true %}
        {% if profile_summary is defined %}
        <a href="{{ account.url }}" title="{{ profile_summary|replace("\n", " ") }}">
        {% else %}
        <a href="{{ account.url }}">
        {% endif %}
            <img src="{{ account.avatar_static }}"
                onerror="(async () => {this.onerror=null;this.src=`https://web.archive.org/web/0/${this.src}`;})();"
            ></img>
            <div class="vertical">
                <span class="name">{{ account.display_name }}</span>
                <span class="at">@{{ account.username }}@{{ instance }}</span>
            </div>
        </a>
    {% endautoescape %}
    </div>
    <div>
        {% if in_reply_to_id %}
            <span class="replyto">Replying to <a class="prev" href="">{{ in_reply_to_account_id }}</a>:</span>
        {% endif %}
        <p>{{ content }}</p>
    </div>
    <div class="media" style="display: none;">
    {% for media in media_attachments %}
    <a href="{{ uri }}" data-href-orig="{{ media.url }}" target="_blank">
        <img class="img count{{ media_attachments|length }}"
                onerror="(async () => {this.onerror=null;this.src=`https://web.archive.org/web/0/${this.src}`;})();"
            src="{{ media.preview_url }}"
        ></img>
    </a>
    {% endfor %}
    </div>
    <a href="{{ url }}" target="_blank">{{ created_at }}</a>
</blockquote>"""))

    @dataclasses.dataclass(unsafe_hash=True)
    class PostRef():
        instance: str = dataclasses.field(hash=True)
        post_id: str = dataclasses.field(hash=True)
        user_id: typing.Optional[str] = dataclasses.field(default=None)

    def login(self: typing.Self) -> None:
        pass

    def seasonPostReference(self, json_obj, post_reference: PostReference) -> None:
        user_id = post_reference.user_id or json_obj['account']['username']
        post_reference.user_id = user_id

    @classmethod
    def getPostFilePath(cls, json_obj, post_reference: PostRef, makedirs=True, media_id=None):  # type: ignore[override]
        user_id = post_reference.user_id or json_obj['account']['username']
        if user_id is None:
            raise NotImplementedError("Post reference must have user set to be saved!")
        # backwash
        post_reference.user_id = user_id

        dest_dir = os.path.join(f"{cls.NOUN_POST}s", post_reference.instance, user_id)

        if makedirs:
            os.makedirs(dest_dir, exist_ok=True)

        filename = f"s{post_reference.post_id}.json"
        if media_id:
            filename = f"s{post_reference.post_id}-{media_id}"

        return os.path.join(dest_dir, filename)

    @staticmethod
    def getRealSourceUrl(media_entry):
        if media_entry['type'] == "image":
            return html.escape(media_entry['url'])
        elif media_entry['type'] == "video":
            return html.escape(media_entry['url'])
        elif media_entry['type'] == "gifv":
            return html.escape(media_entry['url'])

    def getPostMedia(self: typing.Self, json_obj) -> typing.Iterable[typing.Tuple[str, str]]:
        try:
            for media in json_obj["media_attachments"]:
                src = self.getRealSourceUrl(media)
                __, mname = os.path.split(src)
                yield (mname, src)
        except KeyError as e:
            logging.error(json_obj, exc_info=False)
            raise e

    def getTootJsonApi(self: typing.Self, post_reference: PostRef, reason="") -> WorkResult:
        try:
            resp = requests.get(f"https://{post_reference.instance}/api/v1/statuses/{post_reference.post_id}")
            status_json = resp.json()
            if status_json.get('error'):
                logging.error(status_json, exc_info=False)
                raise ValueError(status_json.get('error'))
        except requests.exceptions.JSONDecodeError:
            logging.error((resp, resp.url, resp.headers, resp.text), exc_info=False)
            raise
        logging.warning(f"Downloaded new {self.NOUN_POST} for {post_reference} ({reason})")
        return WorkResult(status_json, nontrivial=True)
        # return status_json

    JSON_GETTERS = [*PermaSocial.JSON_GETTERS, getTootJsonApi]
    # JSON_GETTERS = [getTootJsonApi]

    def getRelatedPosts(self, post_json: dict, post_reference: PostRef) -> typing.Iterable[PostRef]:  # type: ignore[override]
        if parent_id := post_json.get('in_reply_to_id'):
            yield self.PostRef(user_id=None, post_id=parent_id, instance=post_reference.instance)

        # "Quote" support
        body_soup = bs4.BeautifulSoup(post_json['content'], features="lxml")
        for link in body_soup.findAll("a"):
            if match := re.match(self.LINK_RE, link['href']):
                yield self.PostRef(**match.groupdict())

        # raise NotImplementedError

def tw_entities(text, id, entities, extended_entities):
    entities.update(extended_entities)

    text = ""

    try:

        media = entities.get('media', [])
        media_count = len(media)
        for e in media:
            if e['type'] == "photo":
                repl = f"""<a href="{e.get('expanded_url') or PermaTwitter.getRealSourceUrl(e)}" target="_blank">
    <img class="img count{media_count}" src="{PermaTwitter.getRealSourceUrl(e)}"
         """ + """onerror="(async () => {this.onerror=null;this.src=`https://web.archive.org/web/0/${this.src}`;\\})();"
    ></img>
</a>"""
            elif e['type'] == "video" or e['type'] == "hls":
                repl = f"""<video src="{PermaTwitter.getRealSourceUrl(e)}" controls="true"></video>"""
            elif e['type'] == "animated_gif":
                repl = f"""<video src="{PermaTwitter.getRealSourceUrl(e)}" loop="true" playsinline="true" controls="true" preload="auto"></video>"""
            else:
                raise NotImplementedError(e['type'])
                # if DEBUG:
                #     ET.fromstring(repl)
            text += repl
    except ET.ParseError as e:
        logging.error(repl)
        raise e

    return text

def tw_stripents(text, id, entities, extended_entities):
    entities.update(extended_entities)

    for e in entities.get('urls', []):
        find = e.get('url')
        if find:
            src = html.escape(e.get('expanded_url') or PermaTwitter.getRealSourceUrl(e))
            repl = f"<a href='{src}' target='_blank'>{html.escape(e['display_url'])}</a>"
            # if DEBUG:
            #     try:
            #         ET.fromstring(repl)
            #     except ET.ParseError:
            #         logging.error(repl, exc_info=True)
            text = text.replace(find, repl)

    for e in entities.get('media', []):
        find = e.get('url')
        if find:
            text = text.replace(find, "")

    return text

env.filters['tw_entities'] = tw_entities
env.filters['tw_stripents'] = tw_stripents
envUnstrict.filters['tw_entities'] = tw_entities
envUnstrict.filters['tw_stripents'] = tw_stripents

class PermaTwitter(PermaSocial):
    NOUN_POST = "tweet"
    LINK_RE = r"(https|http)://(www.){0,1}(twitter|x)\.com/(?P<user_id>[^/]+)/status/(?P<post_id>\d+).*?"

    EMBED_TEMPLATE = env.from_string(
        """{{ user.screen_name }}: {{ full_text|replace("\n\n", " - ")|replace("\n", " - ") }}]"""
        """(https://twitter.com/{{ user.screen_name }}/status/{{ post_id }}"""  # )
    )

    POST_HTML_TEMPLATE = envUnstrict.from_string(re.sub(r'\n +', '', """<blockquote class="twitter-tweet" data-tweetid="{{id_str}}" data-lang="en" data-dnt="true" data-nosnippet="true" {{ extra_attrs }}>
    <div class="header"
      {% if in_reply_to_screen_name %}data-reply="{{in_reply_to_screen_name}}/{{in_reply_to_status_id_str}}"{% endif %}
    >
    {% autoescape true %}
        {% if retweeted_by %}
            <span class="rtby"><a href="https://twitter.com/{{ retweeted_by.screen_name }}/" title="{{ retweeted_by.description|replace("\n", " ") }}">{{ retweeted_by.name }}</a></span>
        {% endif %}
        <a href="https://twitter.com/{{ user.screen_name }}/" title="{{ user.description|replace("\n", " ") }}">
            <img src="{{ user.profile_image_url_https or 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==' }}"
                onerror="(async () => {this.onerror=null;const newsrc=`https://web.archive.org/web/0/${this.src}`;console.log(this, this.src, newsrc);this.src=newsrc;})();"
            ></img>
            <div class="vertical">
                <span class="name">{{ user.name }}</span>
                <span class="at">@{{ user.screen_name }}</span>
            </div>
        </a>
    {% endautoescape %}
    </div>
    <div>
        {% if in_reply_to_status_id %}
            <span class="replyto">Replying to <a class="prev" href="https://twitter.com/{{in_reply_to_screen_name}}/status/{{ in_reply_to_status_id }}">{{in_reply_to_screen_name}}</a>:</span>
        {% endif %}
        <p>{{ full_text|e|replace("\n\n", "</p><p>")|replace("\n", "</p><p>")|tw_stripents(id, entities or {}, extended_entities or {})|replace("&amp;", "&")|replace("&amp;", "&") }}</p>
    </div>
    <div class="media" style="display: none;">{{ full_text|e|tw_entities(id, entities or {}, extended_entities or {}) }}</div>
    <a href="https://twitter.com/{{ user.screen_name }}/status/{{ post_id }}" target="_blank">{{ created_at }}</a>
</blockquote>"""))

    NITTER_CACHE: typing.Mapping[PostReference, typing.Any] = {}

    @staticmethod
    def getRealSourceUrl(media_entry):
        if media_entry['type'] == "photo":
            return html.escape(media_entry.get('media_url_https') or media_entry.get('media_url'))
        if media_entry['type'] == "hls":
            return media_entry.get('media_url_https') or media_entry.get('media_url')

        elif media_entry['type'] == "video" or media_entry['type'] == "animated_gif":
            best = next(filter(
                lambda v: '.m3u8' not in v['url'].split('/')[-1],
                media_entry['video_info']['variants']
            ))
            return html.escape(best['url'])
        else:
            raise NotImplementedError(media_entry['type'])

    def login(self: typing.Self) -> None:
        tweepy_config_path = os.path.abspath("./tweepy_config.py")
        sys.path.insert(0, os.path.dirname(tweepy_config_path))
        import tweepy_config

        self.NITTR_HOST = tweepy_config.NITTR_HOST or "https://nitter.net"

        auth = tweepy.OAuthHandler(tweepy_config.TWEEPY_CONSUMER_KEY, tweepy_config.TWEEPY_CONSUMER_SECRET)
        auth.set_access_token(tweepy_config.TWEEPY_ACCESS_TOKEN, tweepy_config.TWEEPY_ACCESS_TOKEN_SECRET)
        self._api = tweepy.API(auth, wait_on_rate_limit=True)
        logging.info("Logged in to twitter via Tweepy")

    def getPostMedia(self: typing.Self, json_obj) -> typing.Iterable[typing.Tuple[str, typing.Union[str, typing.Callable]]]:
        for media in json_obj["entities"].get("media", []):
            src = self.getRealSourceUrl(media)
            __, mname = os.path.split(src)
            if media['type'] == "hls":
                def closure(media_dest_path: str) -> None:
                    logging.warning("DL HLS", src, '->', media_dest_path)
                    subprocess.run([
                        'yt-dlp',
                        src,
                        '-o',
                        media_dest_path
                    ])
                yield (mname, closure)
            else:
                yield (mname, src)

    def ensureTweetComplete(self, json_obj, path_if_changed=None):
        # global dest_path
        # Text may be an empty string
        full_text = json_obj.get('full_text')  # or json_obj.get('text')
        if full_text is None:
            full_text = json_obj.get('text')
        has_note = ('… https://t.co/' in full_text) and (
            any(
                (url['expanded_url'] == f"https://twitter.com/i/web/status/{json_obj['id']}")
                for url in e['urls']
            )
            for e in json_obj['entities']
        )
        if has_note and not json_obj.get('full_text_orig'):
            if not self.NITTR_HOST:
                raise NotImplementedError("Tweet needs note_tweet saved, but no NITTR_HOST set!")

            nittr_url = '/'.join([self.NITTR_HOST, json_obj['user']['screen_name'], 'status', json_obj['id_str']])
            logging.warning(f"Using nittr to get full_text for {json_obj['id_str']} from {nittr_url=} b/c {json_obj.get('full_text_orig')=}")
            # logging.warning(json_obj)
            resp = requests.get(nittr_url, headers={'User-Agent': 'curl/8.0.1'})
            try:
                resp.raise_for_status()
            except Exception:
                logging.error(resp.text)
                raise
            soup = bs4.BeautifulSoup(resp.text, features="lxml")
            try:
                note_tweet = soup.select('.tweet-content.media-body')[0].text
                json_obj['full_text_orig'] = json_obj['full_text']
                json_obj['full_text'] = str(note_tweet)
                if path_if_changed:
                    logging.warning(f"Resaving {path_if_changed} with added data")
                    with open(path_if_changed, "w") as fp:
                        json.dump(json_obj, fp, indent=2)
            except IndexError:
                logging.warning("Tweet did not have note? Check has_note logic")
                logging.warning(soup.select('.tweet-content.media-body'))
        return json_obj

    def getPostJsonTweepy(self: typing.Self, post_reference: PostReference, reason="") -> WorkResult:
        if not self.api:
            raise FileNotFoundError("API configuration must be passed in to use network functionality")

        # logging.warning(f"Using twitter to get status for {reason}")
        status = self.api.get_status(post_reference.post_id, tweet_mode='extended')
        logging.warning("Downloaded new tweet for id " + post_reference.post_id)

        json_obj = self.ensureTweetComplete(status._json)

        return json_obj

    def getTweetJsonGalleryDl(self: typing.Self, post_reference: PostReference, reason="") -> WorkResult:
        # TwitterTweetExtractor.tweets of <gallery_dl.extractor.twitter.TwitterTweetExtractor
        # Configured with system defaults, probably %APPDATA%\gallery-dl\config.json
        gallery_dl.config.load()
        extractor = gallery_dl.extractor.find(f"https://twitter.com/{post_reference.user_id}/status/{post_reference.post_id}")
        extractor.initialize()
        extractor._init()
        extractor.log = logging
        try:
            [*extractor.items()]
        except (StopIteration, KeyError):
            pass

        extracted = [*extractor.tweets()][0]
        json_obj = extracted['legacy']
        json_obj['user'] = extracted['core']['user_results']['result']['legacy']
        json_obj['user'] = json_obj['user'] or extractor._user_obj

        return WorkResult(json_obj, nontrivial=True)  # (json_obj_main, json_objs)

    def getTweetJsonNittr(self: typing.Self, post_reference: PostReference, reason="") -> WorkResult:
        if not self.NITTR_HOST:
            raise NotImplementedError("Tweet needs note_tweet saved, but no NITTR_HOST set!")

        if self.NITTER_CACHE.get(post_reference):
            return self.NITTER_CACHE[post_reference]

        nittr_url = '/'.join([self.NITTR_HOST, post_reference.user_id, 'status', post_reference.post_id])

        logging.warning(f"Fetching nittr {post_reference=} {nittr_url=}")

        soup = None
        resp = requests.get(
            nittr_url,
            headers={'User-Agent': 'curl/8.0.1'},
            cookies={'hlsPlayback': 'on'}
        )
        try:
            resp.raise_for_status()
            soup = bs4.BeautifulSoup(resp.text, features="lxml")
        except Exception:
            logging.warning(f"Using flaresolvrr for {nittr_url=}")

            logging.error((resp, resp.headers, resp.text))
            resp = requests.post('http://garnet:8191/v1', json={
                "cmd": "request.get",
                "url": nittr_url,
                "cookies": {'hlsPlayback': 'on'},
                "maxTimeout": 60000
            })
            logging.info(resp)
            resp.raise_for_status()

            resp_json = resp.json()
            soup = bs4.BeautifulSoup(resp_json.get('solution').get('response'))

        def getNittrTweetObj(tweet_el):
            # print(tweet_el)
            json_obj = {
                'id': post_reference.post_id,
                'user': {'screen_name': post_reference.user_id},
                'entities': {
                    "hashtags": [],
                    "symbols": [],
                    "user_mentions": [],
                    "urls": [],
                    "media": [],
                }
            }

            import posixpath
            path_str = urllib.parse.urlparse(tweet_el.select('.tweet-date a')[0]['href']).path

            json_obj['id'] = posixpath.split(path_str)[-1]
            json_obj['user']['screen_name'] = str(tweet_el.select('.tweet-header .username')[0]['title'][1:])
            json_obj['user']['name'] = str(tweet_el.select('.tweet-header .fullname')[0]['title'])

            json_obj['created_at'] = str(tweet_el.select('.tweet-date a[title]')[0]['title'])
            json_obj['full_text'] = str(tweet_el.select('.tweet-content.media-body')[0].text)

            for media_el in tweet_el.select('.attachments .attachment.image'):
                href = urllib.parse.urljoin(self.NITTR_HOST, media_el.find('a', class_='still-image')['href'])
                json_obj['entities']['media'].append({
                    "type": "photo",
                    "expanded_url": href,
                    "media_url": href,
                    "media_url_https": href
                })

            for media_el in tweet_el.select(".attachments video"):
                try:
                    href = urllib.parse.urljoin(self.NITTR_HOST, media_el['data-url'])
                    json_obj['entities']['media'].append({
                        "type": "hls",
                        "expanded_url": href,
                        "media_url": href,
                        "media_url_https": href
                    })
                except KeyError:
                    continue  # no data-url
            return json_obj

        # json_objs = []

        json_obj_main = None
        for tweet_el in soup.select('.main-tweet'):
            json_obj_main = getNittrTweetObj(tweet_el)

        for tweet_el in soup.select('.timeline-item .tweet-body'):
            extra_obj = getNittrTweetObj(tweet_el)
            extra_ref = PostReference(extra_obj['user']['screen_name'], extra_obj['id'])
            self.NITTER_CACHE[extra_ref] = extra_obj

        if json_obj_main:
            return WorkResult(json_obj_main, nontrivial=True)  # (json_obj_main, json_objs)
        else:
            raise ValueError(nittr_url)

    def getTweetInternetArchive(self: typing.Self, post_reference: PostReference, reason="") -> WorkResult:
        ia_url = f"http://web.archive.org/web/1im_/https://twitter.com/{post_reference.user_id}/status/{post_reference.post_id}"
        resp = requests.get(ia_url)

        try:
            resp.raise_for_status()
        except Exception:
            print(resp.text)
            raise
        soup = bs4.BeautifulSoup(resp.text, features="lxml")

        jstweets = soup.select(f'[data-tweet-id="{post_reference.post_id}"]', limit=1)

        if jstweets:
            jstweet = jstweets[0]
            json_obj = {
                "id_str": str(post_reference.post_id),
                "id": post_reference.post_id,
                "user": {
                    "screen_name": jstweet.get('data-screen-name'),
                    "name": jstweet.get('data-name')
                },
                "entities": {
                    "hashtags": [],
                    "symbols": [],
                    "user_mentions": [],
                    "urls": [],
                    "media": []
                },
                "full_text": jstweet.find(class_="js-tweet-text").text,
                "created_at": jstweet.select(".permalink-header .time a [data-time-ms]")[0].get('data-time-ms')
            }
            for image in jstweet.select('[data-image-url]'):
                json_obj['entities']['media'].append({
                    "type": "photo",
                    "media_url": image.get("data-image-url"),
                    "media_url_https": image.get("data-image-url")
                })
            return WorkResult(json_obj, nontrivial=True)

        raise NotImplementedError(ia_url)

    JSON_GETTERS = [
        *PermaSocial.JSON_GETTERS,
        # getPostJsonTweepy,
        timeout_decorator.timeout(10, use_signals=False)(getTweetJsonGalleryDl),
        # getTweetJsonNittr,
        getTweetInternetArchive,
        getTweetJsonGalleryDl
    ]
    # JSON_GETTERS = [*PermaSocial.JSON_GETTERS, getTweetInternetArchive]

    def getRelatedPosts(self, post_json: dict, post_reference: PostReference) -> typing.Iterable[PostReference]:
        if post_json.get("in_reply_to_status_id_str"):
            yield PostReference(post_json['in_reply_to_screen_name'], post_json['in_reply_to_status_id_str'])

        if post_json.get("quoted_status"):
            yield PostReference(post_json["quoted_status"]['user']['screen_name'], post_json["quoted_status"]['id'])


class PermaSocialNew(PermaSocial):
    NOUN_POST = "post"
    LINK_RE = r"(https|http)://(www.){0,1}(?P<user_id>[^/]+)(?P<post_id>[^ )]+)"

    EMBED_TEMPLATE = env.from_string(
        """{{ author.handle }}: {{ record.text|replace("\n\n", " - ")|replace("\n", " - ") }}]"""
        """(https://bsky.app/profile/{{ author.handle }}/post/{{ url_id }}"""  # )
    )

    POST_HTML_TEMPLATE = env.from_string(re.sub(r'\n +', '', """"""))

    def login(self: typing.Self) -> None:
        raise NotImplementedError

    def getPostMedia(self: typing.Self, json_obj) -> typing.Iterable[typing.Tuple[str, typing.Union[str, typing.Callable]]]:
        raise NotImplementedError

    def getPostJsonApi(self: typing.Self, post_reference: PostReference, reason="") -> WorkResult:
        raise NotImplementedError

    JSON_GETTERS = [*PermaSocial.JSON_GETTERS, getPostJsonApi]

    def getRelatedPosts(self, post_json: dict, post_reference: PostReference) -> typing.Iterable[PostReference]:
        raise NotImplementedError

# Can't curry these or the pickler gets mad :(


class PelicanSkeetEmbedMdExtension(markdown.Extension):
    def extendMarkdown(self, md):
        md.inlinePatterns.register(
            PermaBluesky().embedprocessor(markdown.inlinepatterns.IMAGE_LINK_RE, md),
            'skeet_embed',
            200
        )


class PelicanMastoEmbedMdExtension(markdown.Extension):
    def extendMarkdown(self, md):
        md.inlinePatterns.register(
            PermaMastodon().embedprocessor(markdown.inlinepatterns.IMAGE_LINK_RE, md),
            'toot_embed',
            200
        )

class PelicanTweetEmbedMdExtension(markdown.Extension):
    def extendMarkdown(self, md):
        md.inlinePatterns.register(
            PermaTwitter().embedprocessor(markdown.inlinepatterns.IMAGE_LINK_RE, md),
            'tweet_embed',
            200
        )

def pelican_init(pelican_object):
    logging.info("pelican_init")
    pelican_object.settings['MARKDOWN'].setdefault('extensions', []) \
        .append(PelicanSkeetEmbedMdExtension())
    pelican_object.settings['MARKDOWN'].setdefault('extensions', []) \
        .append(PelicanMastoEmbedMdExtension())
    pelican_object.settings['MARKDOWN'].setdefault('extensions', []) \
        .append(PelicanTweetEmbedMdExtension())


def register():
    """Plugin registration"""
    logging.info("register")
    signals.initialized.connect(pelican_init)


if __name__ == "__main__":
    socials = [PermaTwitter(), PermaBluesky(), PermaMastodon()]

    for globstr in sys.argv[1:]:
        for filepath in glob.glob(globstr, recursive=True):
            for social in socials:
                try:
                    social.replaceBlanksInFile(filepath)
                except Exception:
                    traceback.print_exc()
                    continue
