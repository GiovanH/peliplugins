# -*- coding: utf-8 -*-
import json
import logging
import markdown
import os
import re
import xml.etree.ElementTree as ET
import html
import glob
import urllib.parse
import urllib.request
import requests
import bs4

from jinja2 import Environment
# from pelican import generators
from pelican import signals

TOOTLINK_RE = r"(https|http)://([^/]+)/@([^/]+)/(\d+).*?"
TOOTEMBED_NOTITLE_RE = r"(?<=\!\[\]\()" + TOOTLINK_RE + r"(?=\))"

TOOT_FALLBACK_GLOB = None
TOOT_FALLBACK_ON = False
TOOT_FALLBACK_DICT = {}

TOOT_RECURSE_THREADS = True
TOOT_RECURSE_QRTS = True

TOOT_DOWNLOAD_IMAGE_BACKLOG = False
TOOT_DOWNLOAD_IMAGES = True

DEBUG = False

# TODO: Clear support for *both* standalone and embeds
# TODO: Standard retweets show RT and partial text
# TODO: Some characters (>) are double-escaped

TOOT_TEMPLATE_STR = re.sub(r'\n +', '', """<blockquote class="fediverse-toot" data-lang="en" data-dnt="true" data-nosnippet="true" {{ extra_attrs }}>
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
</blockquote>""")


def summarize_html(html_code):
    # logging.warning(html_code)
    soup = bs4.BeautifulSoup(html_code, features="lxml")
    return soup.text


def get_real_src_url(media_entry):
    if media_entry['type'] == "image":
        return html.escape(media_entry['url'])
    elif media_entry['type'] == "video":
        return html.escape(media_entry['url'])
    elif media_entry['type'] == "gifv":
        return html.escape(media_entry['url'])

    # elif media_entry['type'] == "video" or media_entry['type'] == "animated_gif":
    #     best = next(filter(
    #         lambda v: '.m3u8' not in v['url'].split('/')[-1],
    #         media_entry['video_info']['variants']
    #     ))
    #     return html.escape(best['url'])
    else:
        raise NotImplementedError(media_entry['type'])

# def tw_entities(text, id, entities, extended_entities):
#     entities.update(extended_entities)

#     text = ""

#     try:

#         media = entities.get('media', [])
#         media_count = len(media)
#         for e in media:
#             if e['type'] == "photo":
#                 repl = f"""<a href="{e['expanded_url']}" target="_blank">
#     <img class="img count{media_count}" src="{get_real_src_url(e)}"
#         onerror="this.onerror=null;this.src=`https://web.archive.org/web/0/${{this.src}}`;"
#     ></img>
# </a>"""
#             elif e['type'] == "video":
#                 repl = f"""<video src="{get_real_src_url(e)}" controls="true"></video>"""
#             elif e['type'] == "animated_gif":
#                 repl = f"""<video src="{get_real_src_url(e)}" loop="true" playsinline="true" controls="true" preload="auto"></video>"""
#             else:
#                 raise NotImplementedError(e['type'])
#                 if DEBUG:
#                     ET.fromstring(repl)
#             text += repl
#     except ET.ParseError as e:
#         print(repl)
#         raise e

#     return text

# def tw_stripents(text, id, entities, extended_entities):
#     entities.update(extended_entities)

#     for e in entities.get('urls', []):
#         find = e['url']
#         src = html.escape(e['expanded_url'])
#         repl = f"<a href='{src}' target='_blank'>{html.escape(e['display_url'])}</a>"
#         if DEBUG:
#             try:
#                 ET.fromstring(repl)
#             except ET.ParseError:
#                 logging.error(repl, exc_info=True)
#         text = text.replace(find, repl)

#     for e in entities.get('media', []):
#         find = e['url']
#         text = text.replace(find, "")

#     return text


env = Environment()

# env.filters['tw_entities'] = tw_entities
# env.filters['tw_stripents'] = tw_stripents

TOOT_TEMPLATE = env.from_string(TOOT_TEMPLATE_STR)

def pelican_init(pelican_object):
    global TOOT_FALLBACK_GLOB
    global TOOT_FALLBACK_ON
    global TOOT_FALLBACK_DICT
    global TOOT_FALLBACK_MATCH

    global TOOT_RECURSE_THREADS
    global TOOT_RECURSE_QRTS
    global TOOT_DOWNLOAD_IMAGE_BACKLOG
    global TOOT_DOWNLOAD_IMAGES

    TOOT_FALLBACK_ON = pelican_object.settings.get('TOOT_FALLBACK_ON', TOOT_FALLBACK_ON)
    TOOT_DOWNLOAD_IMAGE_BACKLOG = pelican_object.settings.get('TOOT_DOWNLOAD_IMAGE_BACKLOG', TOOT_DOWNLOAD_IMAGE_BACKLOG)
    TOOT_FALLBACK_MATCH = pelican_object.settings.get(
        'TOOT_FALLBACK_MATCH',
        lambda path: re.match(r".*s(\d+)\.json", path).groups(1)
    )

    if TOOT_FALLBACK_ON:
        TOOT_FALLBACK_GLOB = pelican_object.settings['TOOT_FALLBACK_GLOB']

        logging.info("Toot fallback map test:")
        for path in glob.iglob(TOOT_FALLBACK_GLOB, recursive=True):
            logging.info("%s -> %s", path, TOOT_FALLBACK_MATCH(path))
            break

        logging.info("Building tweet fallback library...")
        TOOT_FALLBACK_DICT = {
            TOOT_FALLBACK_MATCH(path): path
            for path in glob.glob(TOOT_FALLBACK_GLOB, recursive=True)
        }

    os.makedirs("toots", exist_ok=True)

    pelican_object.settings['MARKDOWN'].setdefault('extensions', []).append(PelicanFediverseEmbedMdExtension())


class TootEmbedProcessor(markdown.inlinepatterns.LinkInlineProcessor):
    """ Return a img element from the given match. """

    def handleMatch(self, m, data):
        title, index, handled = self.getText(data, m.end(0))
        if not handled:
            return None, None, None

        href, instance, username, toot_id, title, index, handled = self.getLink(data, index)
        if not handled:
            return None, None, None

        # if not title:
        #     logging.warning(f"Tweet {username}/{tweet_id} is missing its title!")

        try:
            toot_json = getTootJson(instance, username, toot_id, get_media=True)
        # except TweepyException as e:
        #     logging.error(f"Can't load tweet {username}/status/{tweet_id}: '{e}'")
        #     reason = e.response.text
        #     if e.response.status_code == 144:
        #         reason = "Tweet has been deleted"
        #     return ET.fromstring(f"<p>Couldn't find tweet <a href='{href}'>'{title or tweet_id}'</a> ({reason})</p>"), m.start(0), index

        except:
            logging.error("Can't load toot %s %s %s", (instance, username, toot_id), exc_info=True)
            return ET.fromstring(f"<p>ERROR! Can't load toot <a href='{href}'>'{title}'</a></p>"), m.start(0), index

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

        string = toot_id  # For error case only
        extra_attrs = " ".join([
            f'data-{k}="{v}"' for k, v in
            dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(href).query)).items()
        ])
        try:
            string = TOOT_TEMPLATE.render(
                md_title=title,
                instance=instance,
                extra_attrs=extra_attrs,
                profile_summary=summarize_html(toot_json.get('account', {}).get('note') or ""),
                **toot_json
            )
            return self.md.htmlStash.store(string), m.start(0), index
        except Exception as e:
            logging.error(string, exc_info=True)
            return None, None, None
            # raise e

    def getLink(self, data, index):
        href, title, index, handled = super().getLink(data, index)
        if handled:
            match = re.match(TOOTLINK_RE, href)
            if match:
                protocol, instance, username, toot_id = match.groups()
                return href, instance, username, toot_id, title, index, handled
        return None, None, None, None, None, None, None


class PelicanFediverseEmbedMdExtension(markdown.Extension):
    def extendMarkdown(self, md):
        # logging.debug("Registering tweet_embed markdown pattern")
        md.inlinePatterns.register(TootEmbedProcessor(markdown.inlinepatterns.IMAGE_LINK_RE, md), 'fediverse_embed', 200)

def urlretrieve(src, dest):
    try:
        opener = urllib.request.build_opener()
        opener.addheaders = [('User-agent', 'curl/8.0.1')]
        urllib.request.install_opener(opener)

        return urllib.request.urlretrieve(src, dest)
    except Exception as e:
        try:
            return urllib.request.urlretrieve('https://web.archive.org/web/0im_/' + src, dest)
        except:
            raise e

def getTootJson(instance, username, toot_id, get_media=False):
    toot_id = str(toot_id)
    dest_dir = os.path.join("toots", instance, username)
    dest_path = os.path.join(dest_dir, f"s{toot_id}.json")

    # if not os.path.isfile(dest_path):
    #     old_path = os.path.join("tweets", username[:3].lower(), username, f"s{tweet_id}.json")
    #     loose_path = os.path.join("tweets", f"{tweet_id}.json")
    #     if os.path.isfile(old_path):
    #         logging.info("Found old-style tweet data path " + old_path)
    #         os.makedirs(dest_dir, exist_ok=True)
    #         shutil.move(old_path, dest_path)
    #     elif os.path.isfile(loose_path):
    #         logging.info("Found loose tweet data path " + loose_path)
    #         os.makedirs(dest_dir, exist_ok=True)
    #         shutil.move(loose_path, dest_path)
    #     else:
    #         pass
    #         # Handled in below try
    #         # raise FileNotFoundError(f"{username}, {tweet_id}")

    try:
        with open(dest_path, "r") as fp:
            json_obj = json.load(fp)
            # logging.debug("Found saved tweet data for " + tweet_id)

            # Temporary: Passthrough to RT
            # startswith = json_obj.get("full_text", json_obj.get("text", '')).startswith("RT @")
            # if startswith and (rt_obj := json_obj.get("retweeted_status")):
            #     rt_obj['retweeted_by'] = json_obj.get('user', {})
            #     json_obj = rt_obj

            # logging.warning(f"{TOOT_DOWNLOAD_IMAGES=} {TOOT_DOWNLOAD_IMAGE_BACKLOG=}")
            if TOOT_DOWNLOAD_IMAGES and TOOT_DOWNLOAD_IMAGE_BACKLOG and json_obj.get("media_attachments"):
                try:
                    for media in json_obj["media_attachments"]:
                        src = get_real_src_url(media)
                        __, mname = os.path.split(src)
                        media_dest_path = os.path.join(dest_dir, f"s{json_obj['id']}-{mname}")
                        if not os.path.isfile(media_dest_path):
                            print("DOWN", src, '->', media_dest_path)
                            urlretrieve(src, media_dest_path)
                        # else:
                        #     print("SKIP", src, '->', media_dest_path)

                except Exception as e:
                    print(f"Media error {json_obj.get('id')!r}: {e}")
                    # open(media_dest_path, 'wb')  # touch file

            return json_obj

    except FileNotFoundError:
        # No file yet
        # logging.warning("Not seeing cached tweet for id " + tweet_id)
        # raise

        try:
            # if not api:
            #     raise FileNotFoundError("API configuration must be passed in to use network functionality")

            # status = api.get_status(tweet_id, tweet_mode='extended'))
            status_json = requests.get(f"https://{instance}/api/v1/statuses/{toot_id}").json()
            logging.info("Downloaded new tweet for id " + toot_id)

            os.makedirs(dest_dir, exist_ok=True)
            with open(dest_path, "w") as fp:
                json.dump(status_json, fp, indent=2)

            if TOOT_DOWNLOAD_IMAGES and get_media and status_json.get("media_attachments"):
                try:
                    for media in status_json["media_attachments"]:
                        src = get_real_src_url(media)
                        __, mname = os.path.split(src)
                        media_dest_path = os.path.join(dest_dir, f"s{status_json['id']}-{mname}")
                        if not os.path.isfile(media_dest_path):
                            print("DOWN", src, '->', media_dest_path)
                            urlretrieve(src, media_dest_path)
                        else:
                            print("SKIP", src, '->', media_dest_path)

                except Exception as e:
                    print(f"Media error {status_json.get('id')!r}: {e}")

            # if TWEET_RECURSE_THREADS and status_json.get("in_reply_to_status_id_str"):
            #     logging.info("Also downloading replied-to tweet " + status_json['in_reply_to_status_id_str'])
            #     getTweetJson(status_json['in_reply_to_screen_name'], status_json['in_reply_to_status_id_str'])

            # if TWEET_RECURSE_QRTS and status_json.get("quoted_status"):
            #     logging.info("Also downloading quoted tweet " + status_json.get("quoted_status")['id_str'])
            #     getTweetJson(status_json.get("quoted_status")['user']['screen_name'], status_json.get("quoted_status")['id'])

            return status_json

        # except (TweepyException, AssertionError) as e:
        #     # logging.error(f"Can't load tweet {username}/{tweet_id}: '{e}'")
        #     if TWEET_FALLBACK_ON:
        #         try:
        #             return getTweetJsonFallback(username, tweet_id)
        #         except FileNotFoundError as e2:
        #             logging.error(str(e2), exc_info=False)
        #             raise e
        #     else:
        #         raise
        except Exception:
            logging.error(f"Can't retrieve tweet with id '{tweet_id}'", exc_info=1)
            raise

# def getTweetJsonFallback(username, tweet_id, **kwargs):
#     tweet_id = str(tweet_id)
#     dest_dir = os.path.join("tweets", username)
#     dest_path = os.path.join(dest_dir, f"s{tweet_id}.json")

#     try:
#         src_path = TWEET_FALLBACK_DICT[tweet_id]
#     except KeyError:
#         raise FileNotFoundError(f"'{tweet_id}' not in fallback dictionary")

#     # If we're at the fallback, there shouldn't be a normal file.
#     assert not os.path.isfile(dest_path)

#     # old_path = os.path.join("tweets", username[:3].lower(), username, f"s{tweet_id}.json")
#     if os.path.isfile(src_path):
#         logging.info("Found fallback tweet data path '%s', copying to '%s'", src_path, dest_path)
#         os.makedirs(dest_dir, exist_ok=True)
#         shutil.copy2(src_path, dest_path)
#     else:
#         raise FileNotFoundError(f"'{tweet_id}' in fallback dictionary but not on disk")

#     return getTweetJson(username, tweet_id, **kwargs)


def register():
    """Plugin registration"""
    signals.initialized.connect(pelican_init)


TOOT_EMBED_TEMPLATE = env.from_string("""{{ account.username }}@{{ instance }}: {{ summary|e|replace("\n\n", " - ")|replace("\n", " - ") }}]({{ url }}""")

def replaceBlanksInFile(filepath, replace_only_uncaptioned=True):
    with open(filepath, "r", encoding="utf-8") as fp:
        body = fp.read()

    dirty = False
    for match in re.finditer(TOOTEMBED_NOTITLE_RE, body):
        force_uncaptioned_prefix = "![" if replace_only_uncaptioned else ""
        try:
            protocol, instance, username, toot_id = match.groups()
            json_obj = getTootJson(
                instance,
                username,
                toot_id,
                get_media=True
            )
            rendered = TOOT_EMBED_TEMPLATE.render(
                **json_obj,
                summary=summarize_html(json_obj.get('content'))
            )
            whole_md_object = force_uncaptioned_prefix + "](" + match.group(0)

            # logging.warning(f"{whole_md_object!r} -> {rendered!r}")
            body = body.replace(whole_md_object, force_uncaptioned_prefix + rendered)
            dirty = True
        except FileNotFoundError:
            logging.warning(f"No saved info for toot {match!r} {(instance, username, toot_id)!r}", exc_info=False)
        except Exception as e:
            logging.error(e)
            logging.warning(f"{filepath}: Couldn't get toot \n\t{match.group()}")
    
    if dirty:
        with open(filepath, "w", encoding="utf-8") as fp:
            fp.write(body)
    

if __name__ == "__main__":
    import sys

    for globstr in sys.argv[1:]:
        for filepath in glob.glob(globstr, recursive=True):
            replaceBlanksInFile(filepath)
