# -*- coding: utf-8 -*-
import logging
import markdown
import os
import re
# import atproto
import xml.etree.ElementTree as ET
import glob
import urllib.parse
import urllib.request
import functools
import netrc
import chitose

try:
    import ujson as json
except ImportError:
    import json

from jinja2 import Environment
# from pelican import generators
from pelican import signals

SKEETLINK_RE = r"(https|http)://(www.){0,1}bsky.app/profile/([^/]+)/post/(.+)"
SKEETEMBED_NOTITLE_RE = r"(?<=\!\[\]\()" + SKEETLINK_RE + r"(?=\))"

DEBUG = False

SKEET_DOWNLOAD_IMAGES = True
SKEET_DOWNLOAD_IMAGE_BACKLOG = True

SKEET_TEMPLATE_STR = re.sub(r'\n +', '', """<blockquote class="twitter-tweet" data-lang="en" data-dnt="true" data-nosnippet="true" {{ extra_attrs }}>
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
        <p>{{ record.text|e|replace("\n\n", "</p><p>")|replace("\n", "</p><p>") }}</p>
    </div>
    <div class="media" style="display: none;">{{ full_text|e|tw_entities(embed.images) }}</div>
    <a href="https://bsky.app/profile/{{ author.handle }}/post/{{ id }}" target="_blank">{{ record.createdAt }}</a>
</blockquote>""")

# <!-- {% if not md_title %}!{% endif %}[{{ user.screen_name }}: {{ full_text|e|replace("\n\n", " - ")|replace("\n", " - ") }}](https://twitter.com/{{ user.screen_name }}/status/{{ id }}) -->

env = Environment()

def todict(obj, classkey=None):
    if isinstance(obj, dict):
        data = {}
        for (k, v) in obj.items():
            data[k] = todict(v, classkey)
        return data
    elif hasattr(obj, "_ast"):
        return todict(obj._ast())
    elif hasattr(obj, "__iter__") and not isinstance(obj, str):
        return [todict(v, classkey) for v in obj]
    elif hasattr(obj, "__dict__"):
        data = dict([(key, todict(value, classkey))
            for key, value in obj.__dict__.items()
            if not callable(value) and not key.startswith('_')])
        if classkey is not None and hasattr(obj, "__class__"):
            data[classkey] = obj.__class__.__name__
        return data
    else:
        return obj

def tw_entities(text, images=[]):
    text = ""

    try:

        media_count = len(images)
        for e in images:
            repl = f"""<a href="{e.get('fullsize')}" target="_blank">
    <img class="img count{media_count}" src="{e.get('fullsize')}"
         """ + """onerror="(async () => {this.onerror=null;this.src=`https://web.archive.org/web/0/${this.src}`;\})();"
    ></img>
</a>"""
            text += repl
    except ET.ParseError as e:
        print(repl)
        raise e

    return text

env.filters['tw_entities'] = tw_entities
# env.filters['tw_stripents'] = tw_stripents


SKEET_TEMPLATE = env.from_string(SKEET_TEMPLATE_STR)

BSKY_USER = None
BSKY_PASSWD = None

api = None

def getApi():
    global api
    if api:
        return api

    rc = netrc.netrc()
    (BSKY_USER, _, BSKY_PASSWD) = rc.authenticators("bsky.social")
    api = chitose.BskyAgent(service='https://bsky.social')
    profile = api.login(BSKY_USER, BSKY_PASSWD)
    logging.info(f"Logged in as {profile.displayName}")

    return api


def pelican_init(pelican_object):
    global BSKY_USER
    global BSKY_PASSWD
    BSKY_USER = pelican_object.settings.get('BSKY_USER')
    BSKY_PASSWD = pelican_object.settings.get('BSKY_PASSWD')

    os.makedirs("skeets", exist_ok=True)

    pelican_object.settings['MARKDOWN'].setdefault('extensions', []).append(PelicanSkeetEmbedMdExtension())

class SkeetEmbedProcessor(markdown.inlinepatterns.LinkInlineProcessor):
    """ Return a img element from the given match. """

    def handleMatch(self, m, data):
        title, index, handled = self.getText(data, m.end(0))
        if not handled:
            return None, None, None

        href, username, tweet_id, __, index, handled = self.getLink(data, index)
        if not handled:
            return None, None, None

        # if not title:
        #     logging.warning(f"Skeet {username}/{tweet_id} is missing its title!")

        try:
            tweet_json = getSkeetJson(username, tweet_id, get_media=True, reason=tweet_id)
            # logging.warning("Got tweet json")

        # except TweepyException as e:
        #     logging.error(f"Can't load skeet {username}/status/{tweet_id}: '{e}'")
        #     reason = e.response.text
        #     if e.response.status_code == 144:
        #         reason = "Skeet has been deleted"
        #     return ET.fromstring(f"<p>Couldn't find skeet <a href='{href}'>'{title or tweet_id}'</a> ({reason})</p>"), m.start(0), index

        except:
            logging.error("Can't load skeet " + tweet_id, exc_info=True)
            return ET.fromstring(f"<p>ERROR! Can't load skeet <a href='{href}'>'{title}'</a></p>"), m.start(0), index

        # try:
        #     # Legacy support:
        #     tweet_json['entities'] = tweet_json.get('entities', {})
        #     tweet_json['full_text'] = tweet_json.get('full_text', tweet_json.get('text'))
        #     tweet_json['extended_entities'] = tweet_json.get('extended_entities', {})
        #     tweet_json['user'] = tweet_json.get('user', {})
        #     tweet_json['user']['screen_name'] = tweet_json['user'].get('screen_name', 'unknown')

        # except:
        #     logging.error("Can't load tweet " + tweet_id, exc_info=True)
        #     return ET.fromstring(f"<p>ERROR! Can't load tweet <a href='{href}'>'{title}'</a></p>"), m.start(0), index

        string = tweet_id  # For error case only
        extra_attrs = " ".join([
            f'data-{k}="{v}"' for k, v in
            dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(href).query)).items()
        ])
        try:
            string = SKEET_TEMPLATE.render(md_title=title, extra_attrs=extra_attrs, **tweet_json)
            # return ET.fromstring(string), m.start(0), m.end(0)
            return self.md.htmlStash.store(string), m.start(0), index
        except ET.ParseError as e:
            logging.error(string, exc_info=True)
            raise e

    def getLink(self, data, index):
        href, title, index, handled = super().getLink(data, index)
        if handled:
            match = re.match(SKEETLINK_RE, href)
            if match:
                http, www, username, tweet_id = match.groups()
                return href, username, tweet_id, title, index, handled
        return None, None, None, None, None, None


class PelicanSkeetEmbedMdExtension(markdown.Extension):
    def extendMarkdown(self, md):
        # logging.debug("Registering tweet_embed markdown pattern")
        md.inlinePatterns.register(SkeetEmbedProcessor(markdown.inlinepatterns.IMAGE_LINK_RE, md), 'skeet_embed', 200)


def urlretrieve(src, dest):
    try:
        # return urllib.request.urlretrieve(src, dest)
        # import urllib.request

        opener = urllib.request.build_opener()
        opener.addheaders = [('User-agent', 'curl/8.0.1')]
        urllib.request.install_opener(opener)
        urllib.request.urlretrieve(src, dest)
        # resp = requests.get(src, headers={'User-Agent': 'curl/8.0.1'})

    except Exception as e:
        try:
            return urllib.request.urlretrieve('https://web.archive.org/web/0im_/' + src, dest)
        except:
            raise e

@functools.lru_cache()
def getSkeetJson(username, tweet_id, get_media=False, reason=""):
    # global dest_path
    tweet_id = str(tweet_id)
    dest_dir = os.path.join("skeets", username)
    dest_path = os.path.join(dest_dir, f"s{tweet_id}.json")

    json_obj = None

    if not json_obj:
        # Raw file open
        try:
            with open(dest_path, "r") as fp:
                json_obj = json.load(fp)
                # logging.debug("Found saved tweet data for " + tweet_id)

                # Temporary: Passthrough to RT
                startswith = json_obj.get("full_text", json_obj.get("text", '')).startswith("RT @")
                if startswith and (rt_obj := json_obj.get("retweeted_status")):
                    rt_obj['retweeted_by'] = json_obj.get('user', {})
                    json_obj = rt_obj

                if SKEET_DOWNLOAD_IMAGES and SKEET_DOWNLOAD_IMAGE_BACKLOG and json_obj.get("entities", {}).get("media"):
                    try:
                        for media in json_obj["entities"]["media"]:
                            src = get_real_src_url(media)
                            __, mname = os.path.split(src)
                            media_dest_path = os.path.join(dest_dir, f"s{json_obj['id']}-{mname}")
                            if not os.path.isfile(media_dest_path):
                                print("DL", src, '->', media_dest_path)
                                urlretrieve(src, media_dest_path)
                            # else:
                            #     print("SKIP", src, '->', media_dest_path)

                    except Exception as e:
                        print(f"Media error {json_obj['id']!r}: {e}")
                        open(media_dest_path, 'wb')  # touch file

                return json_obj

        except (FileNotFoundError, KeyError, json.JSONDecodeError):
            # No file yet, or file missing required keys
            # logging.warning("Not seeing cached tweet for id " + tweet_id)
            # raise
            pass

    if not json_obj:
        try:
            json_obj = getSkeetJsonApi(username, tweet_id, get_media=get_media, reason=reason)
        except Exception:
            logging.error(f"Can't retrieve skeet with id '{tweet_id}'", exc_info=1)
            pass

    if json_obj:
        os.makedirs(dest_dir, exist_ok=True)

        with open(dest_path, "w") as fp:
            json.dump(json_obj, fp, indent=2)

        # if SKEET_RECURSE_THREADS and json_obj.get("in_reply_to_status_id_str"):
        #     logging.info("Also downloading replied-to tweet " + json_obj['in_reply_to_status_id_str'])
        #     getSkeetJson(json_obj['in_reply_to_screen_name'], json_obj['in_reply_to_status_id_str'], reason="reply")

        # if SKEET_RECURSE_QRTS and json_obj.get("quoted_status"):
        #     logging.info("Also downloading quoted tweet " + json_obj.get("quoted_status")['id_str'])
        #     getSkeetJson(json_obj.get("quoted_status")['user']['screen_name'], json_obj.get("quoted_status")['id'], reason="quoted")

        if SKEET_DOWNLOAD_IMAGES and get_media and json_obj.get("embed", {}).get("images"):
            try:
                for media in json_obj["embed"]["images"]:
                    src = media['fullsize']
                    __, mname = os.path.split(src)
                    media_dest_path = os.path.join(dest_dir, f"s{json_obj['id']}-{mname}")
                    if not os.path.isfile(media_dest_path):
                        urlretrieve(src, media_dest_path)

            except Exception as e:
                print(f"Media error {json_obj['id']!r}: {e}")

        return json_obj
    else:
        raise Exception(f"Can't retrieve skeet with id '{tweet_id}'")

def getSkeetJsonApi(username, tweet_id, get_media=False, reason=""):
    if not getApi():
        raise FileNotFoundError("API configuration must be passed in to use network functionality")

    did = json.loads(getApi().get_profile(actor=username))['did']
    logging.warning(f"Using bluesky to get status at://{did}/app.bsky.feed.post/{tweet_id} for {reason}")
    response = getApi().get_post_thread(uri=f"at://{did}/app.bsky.feed.post/{tweet_id}")
    logging.info("Downloaded new skeet for id " + tweet_id)

    response = json.loads(response)
    response['thread']['post']['id'] = tweet_id
    return response['thread']['post']
    # return {
    #     k: (v if isinstance(v, (str, list, int)) else v.__dict__)
    #     for k, v in {
    #         key: getattr(response.thread.post, key)
    #         for key in
    #         ['author', 'cid', 'embed', 'indexedAt', 'labels', 'likeCount', 'record', 'replyCount', 'repostCount', 'uri']
    #     }.items()
    # }



def register():
    """Plugin registration"""
    signals.initialized.connect(pelican_init)
    # signals.article_generator_write_article.connect(x_generatfetchingor_write_x)
    # signals.page_generator_write_page.connect(x_generator_write_x)


SKEET_EMBED_TEMPLATE = env.from_string("""{{ author.handle }}: {{ record.text|replace("\n\n", " - ")|replace("\n", " - ") }}](https://bsky.app/profile/{{ author.handle }}/post/{{ url_id }}""")


def replaceBlanksInFile(filepath, replace_only_uncaptioned=True):
    with open(filepath, "r", encoding="utf-8") as fp:
        body = fp.read()

    dirty = False
    for match in re.finditer(SKEETEMBED_NOTITLE_RE if replace_only_uncaptioned else SKEETLINK_RE, body):
        force_uncaptioned_prefix = "![" if replace_only_uncaptioned else ""
        try:
            http, www, username, tweet_id = match.groups()
            json_obj = getSkeetJson(username, tweet_id, get_media=True, reason=match)

            rendered = SKEET_EMBED_TEMPLATE.render(url_id=tweet_id, **json_obj)
            whole_md_object = force_uncaptioned_prefix + "](" + match.group(0)

            # logging.warning(f"{whole_md_object!r} -> {rendered!r}")
            body = body.replace(whole_md_object, force_uncaptioned_prefix + rendered)
            dirty = True
        except FileNotFoundError:
            logging.warning(f"No saved info for skeet {match!r} {(username, tweet_id)!r}", exc_info=False)
        except Exception as e:
            logging.error(e, exc_info=True)
            logging.warning(f"{filepath}: Couldn't get skeet \n\t{match.group()}")

    if dirty:
        with open(filepath, "w", encoding="utf-8") as fp:
            fp.write(body)


if __name__ == "__main__":
    import sys

    # from atproto import Client
    try:
        rc = netrc.netrc()
        (BSKY_USER, _, BSKY_PASSWD) = rc.authenticators("bsky.social")
        api = chitose.BskyAgent(service='https://bsky.social')
        profile = api.login(BSKY_USER, BSKY_PASSWD)
        logging.info(f"Logged in as {BSKY_USER}")
    except ImportError:
        logging.warning("Couldn't import , won't have internet functionality!", exc_info=True)
    except Exception:
        import traceback
        traceback.print_exc()
        logging.info("API not configured; using local skeets only.")

    for globstr in sys.argv[1:]:
        print(globstr)
        for filepath in glob.glob(globstr, recursive=True):
            replaceBlanksInFile(filepath)
