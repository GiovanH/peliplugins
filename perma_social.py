import traceback
import netrc
import logging
import glob
import re
import jinja2
import json
import urllib
import markdown
import os
import posixpath
import functools
import collections
import typing
import dataclasses
import requests
import html
import bs4

import markdown
from pelican import signals  # type: ignore[import]
import xml.etree.ElementTree as ET

import chitose  # type: ignore[import]

env = jinja2.Environment()

logging.basicConfig(level=logging.DEBUG)


def summarize_html(html_code):
    # logging.warning(html_code)
    soup = bs4.BeautifulSoup(html_code, features="lxml")
    return soup.text


env.filters['summarize_html'] = summarize_html


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
            traceback.print_stack()
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
                logging.warning(f"{getter!s} Failed to lookup {(post_reference)} for {reason}")
        raise last_exception

    def getPostJsonCached(self, post_reference, reason="Unknown") -> WorkResult:
        dest_path = self.getPostFilePath(dict(), post_reference)
        with open(dest_path, "r") as fp:
            return WorkResult(json.load(fp), nontrivial=False)

    JSON_GETTERS: typing.List[typing.Callable] = [getPostJsonCached]

    def getRealSourceUrl(self, media_url):
        raise NotImplementedError

    def getPostMedia(self, json_obj):
        print(json_obj)
        raise NotImplementedError

    def savePostMedia(self, json_obj, post_reference: PostReference, reason="Unknown"):
        for (mname, src_url) in self.getPostMedia(json_obj):
            try:
                media_dest_path = self.getPostFilePath(json_obj, post_reference, media_id=mname)

                if not os.path.isfile(media_dest_path):
                    print("DL", src_url, '->', media_dest_path)
                    urlretrieve(src_url, media_dest_path)

            except Exception as e:
                print(f"Media error {post_reference}: {e}")
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

                string = repr(post_reference)  # For error case only
                extra_attrs = " ".join([
                    f'data-{k}="{v}"' for k, v in
                    dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(href).query)).items()  # type: ignore[type-var]
                ])
                try:
                    string = superself.POST_HTML_TEMPLATE.render(extra_attrs=extra_attrs, **matches, **json_obj)  # type: ignore[arg-type]
                    # return ET.fromstring(string), m.start(0), m.end(0)
                    return self.md.htmlStash.store(string), m.start(0), index
                except ET.ParseError as e:
                    logging.error(string, exc_info=True)
                    raise e

            def getLink(self, data, index) -> typing.Union[typing.Tuple[str, typing.Mapping[str, str], str, str, bool], typing.Tuple[None, None, None, None, None]]:
                href, title, index, handled = super().getLink(data, index)
                if handled:
                    logging.debug(("saw", href, title, index, handled))
                    # It's an image, but is it a post?
                    match = re.match(superself.LINK_RE, href)
                    if match:
                        logging.debug(("matched", href, title, index, handled))
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
            json_obj = self.getPostJson(post_reference, get_media=True, reason=match)

            rendered = force_uncaptioned_prefix + self.EMBED_TEMPLATE.render(**matches, **json_obj)
            whole_md_object = force_uncaptioned_prefix + "](" + match.group(0)

            logging.debug(f"{whole_md_object!r} -> {rendered!r}")
            body = body.replace(whole_md_object, rendered)
            dirty = True

        if dirty:
            with open(filepath, "w", encoding="utf-8") as fp:
                fp.write(body)


def bs_htmlize(text, facets):
    paragraphs = "<p>" + text.replace("\n\n", "</p><p>").replace("\n", "</p><p>") + "</p>"

    for facet in facets:
        for feature in facet['features']:
            if feature['$type'] == "app.bsky.richtext.facet#link":
                paragraphs = paragraphs.replace(
                    feature['uri'],
                    f"<a href='{feature['uri']}'>{feature['uri']}</a>"
                )
            else:
                raise NotImplementedError(feature['$type'])
    return paragraphs


env.filters['bs_htmlize'] = bs_htmlize


class PermaBluesky(PermaSocial):
    NOUN_POST = "skeet"
    LINK_RE = r"(https|http)://(www.){0,1}bsky.app/profile/(?P<user_id>[^/]+)/post/(?P<post_id>[^ )]+)"

    EMBED_TEMPLATE = env.from_string(
        """{{ author.handle }}: {{ record.text|replace("\n\n", " - ")|replace("\n", " - ") }}]"""
        """(https://bsky.app/profile/{{ author.handle }}/post/{{ post_id }}"""  # )
    )

    POST_HTML_TEMPLATE = env.from_string(re.sub(r'\n +', '', """
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
    <div class="media" style="display: none;">
    {% for e in embed.images %}
    <a href="{{e.fullsize}}" target="_blank">
        <img class="img count{media_count}" src="{{e.fullsize}}"
             onerror="(async () => {this.onerror=null;this.src=`https://web.archive.org/web/0/${this.src}`;})();"
        ></img>
    </a>
    {% endfor %}
    </div>
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
        try:
            thread_response = self.bskyGetThread(post_reference)
            thread_response['thread']['post']['id'] = post_reference.post_id

            logging.info(f"Downloaded new {self.NOUN_POST} for {post_reference} ({reason})")
            # print(thread_response)
            json_obj = thread_response['thread']['post']

            return WorkResult(json_obj, nontrivial=True)

        except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
            logging.error(e.headers)
            logging.error(e.fp.read())
            raise e
        except Exception:
            raise

    def getRelatedPosts(self, post_json: dict, post_reference: PostReference) -> typing.Iterable[PostReference]:
        # return []
        ref = self.PostRef(user_id=post_json['author']['handle'], post_id=post_json['id'])
        thread_response = self.bskyGetThread(ref)
        if parent := thread_response['thread'].get('parent'):
            yield self.bskyPostToRef(parent['post'])

        for reply in thread_response['thread'].get('replies', []):
            yield self.bskyPostToRef(reply['post'])

    JSON_GETTERS = [*PermaSocial.JSON_GETTERS, getSkeetJsonApi]


class PermaMastodon(PermaSocial):
    NOUN_POST = "toot"
    LINK_RE = r"(https|http)://(?P<instance>[^/]+)/@(?P<user_id>[^/]+)/(?P<post_id>[^ )]+)"

    EMBED_TEMPLATE = env.from_string(
        """{{ account.username }}@{{ instance }}: {{ content|summarize_html|e|replace("\n\n", " - ")|replace("\n", " - ") }}]({{ url }}"""  # )
    )

    POST_HTML_TEMPLATE = env.from_string(re.sub(r'\n +', '', """<blockquote class="fediverse-toot" data-lang="en" data-dnt="true" data-nosnippet="true" {{ extra_attrs }}>
    <div class="header">
    {% autoescape true %}
        <a href="{{ account.url }}"title="{{ profile_summary|replace("\n", " ") }}">
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
    def get_real_src_url(media_entry):
        if media_entry['type'] == "image":
            return html.escape(media_entry['url'])
        elif media_entry['type'] == "video":
            return html.escape(media_entry['url'])
        elif media_entry['type'] == "gifv":
            return html.escape(media_entry['url'])

    def getPostMedia(self: typing.Self, json_obj) -> typing.Iterable[typing.Tuple[str, str]]:
        for media in json_obj["media_attachments"]:
            src = self.get_real_src_url(media)
            __, mname = os.path.split(src)
            yield (mname, src)

    def getTootJsonApi(self: typing.Self, post_reference: PostRef, reason="") -> WorkResult:
        status_json = requests.get(f"https://{post_reference.instance}/api/v1/statuses/{post_reference.post_id}").json()
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

    def getPostMedia(self: typing.Self, json_obj) -> typing.Iterable[typing.Tuple[str, str]]:
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


def pelican_init(pelican_object):
    logging.info("pelican_init")
    pelican_object.settings['MARKDOWN'].setdefault('extensions', []) \
        .append(PelicanSkeetEmbedMdExtension())
    # pelican_object.settings['MARKDOWN'].setdefault('extensions', []) \
    #     .append(PelicanMastoEmbedMdExtension())


def register():
    """Plugin registration"""
    logging.info("register")
    signals.initialized.connect(pelican_init)


if __name__ == "__main__":
    import sys

    socials = [PermaBluesky(), PermaMastodon()]

    for globstr in sys.argv[1:]:
        for filepath in glob.glob(globstr, recursive=True):
            for social in socials:
                social.replaceBlanksInFile(filepath)
