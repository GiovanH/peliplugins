# -*- coding: utf-8 -*-
import json
import logging
import markdown
import os
import re
import tweepy
from tweepy.errors import TweepyException
import xml.etree.ElementTree as ET
import html
import shutil
import glob
import urllib.parse
import urllib.request

from jinja2 import Environment
# from pelican import generators
from pelican import signals

TWEETLINK_RE = r"(https|http)://(www.){0,1}twitter\.com/([^/]+)/status/(\d+).*?"
TWEETEMBED_NOTITLE_RE = r"(?<=\!\[\]\()" + TWEETLINK_RE + r"(?=\))"
        

TWEET_FALLBACK_GLOB = None
TWEET_FALLBACK_ON = False
TWEET_FALLBACK_DICT = {}

TWEET_RECURSE_THREADS = True
TWEET_RECURSE_QRTS = True

TWEET_DOWNLOAD_IMAGE_BACKLOG = False
TWEET_DOWNLOAD_IMAGES = True

DEBUG = False

# TODO: Clear support for *both* standalone and embeds
# TODO: Standard retweets show RT and partial text
# TODO: Some characters (>) are double-escaped

# TWEET_TEMPLATE = Template("""<p><blockquote class="twitter-tweet" data-lang="en" data-dnt="true">
# <p lang="und" dir="ltr">{{ full_text }}</p>
# <span>– {{ user.name }} (@{{ user.screen_name }})</span>
# <a href="https://twitter.com/{{ user.screen_name }}/status/{{ id }}">{{ created_at }}</a></blockquote></p>""")

# Add
# <script async="true" src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>
# to your renderdeps!

TWEET_TEMPLATE_STR = re.sub(r'\n +', '', """<blockquote class="twitter-tweet" data-lang="en" data-dnt="true" data-nosnippet="true" {{ extra_attrs }}>
    <div class="header">
    {% autoescape true %}
        {% if retweeted_by %}
            <span class="rtby"><a href="https://twitter.com/{{ retweeted_by.screen_name }}/" title="{{ retweeted_by.description|replace("\n", " ") }}">{{ retweeted_by.name }}</a></span>
        {% endif %}
        <a href="https://twitter.com/{{ user.screen_name }}/" title="{{ user.description|replace("\n", " ") }}">
            <img src="{{ user.profile_image_url_https }}"
                onerror="(async () => {this.onerror=null;this.src=`https://web.archive.org/web/0/${this.src}`;})();"
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
        <p>{{ full_text|e|replace("\n\n", "</p><p>")|replace("\n", "</p><p>")|tw_stripents(id, entities, extended_entities or {})|replace("&amp;", "&") }}</p>
    </div>
    <div class="media" style="display: none;">{{ full_text|e|tw_entities(id, entities, extended_entities or {}) }}</div>
    <a href="https://twitter.com/{{ user.screen_name }}/status/{{ id }}" target="_blank">{{ created_at }}</a>
</blockquote>""")

# <!-- {% if not md_title %}!{% endif %}[{{ user.screen_name }}: {{ full_text|e|replace("\n\n", " - ")|replace("\n", " - ") }}](https://twitter.com/{{ user.screen_name }}/status/{{ id }}) -->

api = None

def get_real_src_url(media_entry):
    if media_entry['type'] == "photo":
        return html.escape(media_entry['media_url_https'])

    elif media_entry['type'] == "video" or media_entry['type'] == "animated_gif":
        best = next(filter(
            lambda v: '.m3u8' not in v['url'].split('/')[-1],
            media_entry['video_info']['variants']
        ))
        return html.escape(best['url'])
    else:
        raise NotImplementedError(media_entry['type'])

def tw_entities(text, id, entities, extended_entities):
    entities.update(extended_entities)

    text = ""

    try:

        media = entities.get('media', [])
        media_count = len(media)
        for e in media:
            if e['type'] == "photo":
                repl = f"""<a href="{e['expanded_url']}" target="_blank">
    <img class="img count{media_count}" src="{get_real_src_url(e)}"
         """+"""onerror="(async () => {this.onerror=null;this.src=`https://web.archive.org/web/0/${this.src}`;\})();"
    ></img>
</a>"""
            elif e['type'] == "video":
                repl = f"""<video src="{get_real_src_url(e)}" controls="true"></video>"""
            elif e['type'] == "animated_gif":
                repl = f"""<video src="{get_real_src_url(e)}" loop="true" playsinline="true" controls="true" preload="auto"></video>"""
            else:
                raise NotImplementedError(e['type'])
                if DEBUG:
                    ET.fromstring(repl)
            text += repl
    except ET.ParseError as e:
        print(repl)
        raise e

    return text

def tw_stripents(text, id, entities, extended_entities):
    entities.update(extended_entities)

    for e in entities.get('urls', []):
        find = e['url']
        src = html.escape(e['expanded_url'])
        repl = f"<a href='{src}' target='_blank'>{html.escape(e['display_url'])}</a>"
        if DEBUG:
            try:
                ET.fromstring(repl)
            except ET.ParseError:
                logging.error(repl, exc_info=True)
        text = text.replace(find, repl)

    for e in entities.get('media', []):
        find = e['url'] 
        text = text.replace(find, "")

    return text


env = Environment()

env.filters['tw_entities'] = tw_entities
env.filters['tw_stripents'] = tw_stripents

TWEET_TEMPLATE = env.from_string(TWEET_TEMPLATE_STR)

def pelican_init(pelican_object):
    consumer_key = pelican_object.settings.get('TWEEPY_CONSUMER_KEY')
    consumer_secret = pelican_object.settings.get('TWEEPY_CONSUMER_SECRET')
    access_token = pelican_object.settings.get('TWEEPY_ACCESS_TOKEN')
    access_token_secret = pelican_object.settings.get('TWEEPY_ACCESS_TOKEN_SECRET')

    global TWEET_FALLBACK_GLOB
    global TWEET_FALLBACK_ON
    global TWEET_FALLBACK_DICT
    global TWEET_FALLBACK_MATCH

    global TWEET_RECURSE_THREADS
    global TWEET_RECURSE_QRTS
    global TWEET_DOWNLOAD_IMAGE_BACKLOG
    global TWEET_DOWNLOAD_IMAGES

    TWEET_RECURSE_THREADS = pelican_object.settings.get('TWEET_RECURSE_THREADS', TWEET_RECURSE_THREADS)
    TWEET_RECURSE_QRTS = pelican_object.settings.get('TWEET_RECURSE_QRTS', TWEET_RECURSE_QRTS)
    TWEET_DOWNLOAD_IMAGE_BACKLOG = pelican_object.settings.get('TWEET_DOWNLOAD_IMAGE_BACKLOG', TWEET_DOWNLOAD_IMAGE_BACKLOG)
    TWEET_DOWNLOAD_IMAGES = pelican_object.settings.get('TWEET_DOWNLOAD_IMAGES', TWEET_DOWNLOAD_IMAGES)

    TWEET_FALLBACK_ON = pelican_object.settings.get('TWEET_FALLBACK_ON', TWEET_FALLBACK_ON)
    TWEET_FALLBACK_MATCH = pelican_object.settings.get(
        'TWEET_FALLBACK_MATCH', 
        lambda path: re.match(r".*s(\d+)\.json", path).groups(1)
    )

    if TWEET_FALLBACK_ON:
        TWEET_FALLBACK_GLOB = pelican_object.settings['TWEET_FALLBACK_GLOB']

        logging.info("Tweet fallback map test:")
        for path in glob.iglob(TWEET_FALLBACK_GLOB, recursive=True):
            logging.info("%s -> %s", path, TWEET_FALLBACK_MATCH(path))
            break

        logging.info("Building tweet fallback library...")
        TWEET_FALLBACK_DICT = {
            TWEET_FALLBACK_MATCH(path): path
            for path in glob.glob(TWEET_FALLBACK_GLOB, recursive=True)
        }
        
    global api
    try:
        assert consumer_key
        auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        auth.set_access_token(access_token, access_token_secret)
        api = tweepy.API(auth, wait_on_rate_limit=True)
        logging.info("Logged in to twitter via Tweepy")
    except:
        logging.info("Tweepy not configured; using local tweets only.")

    os.makedirs("tweets", exist_ok=True)

    pelican_object.settings['MARKDOWN'].setdefault('extensions', []).append(PelicanTweetEmbedMdExtension())


class TweetEmbedProcessor(markdown.inlinepatterns.LinkInlineProcessor):
    """ Return a img element from the given match. """

    def handleMatch(self, m, data):
        title, index, handled = self.getText(data, m.end(0))
        if not handled:
            return None, None, None

        href, username, tweet_id, __, index, handled = self.getLink(data, index)
        if not handled:
            return None, None, None

        # if not title:
        #     logging.warning(f"Tweet {username}/{tweet_id} is missing its title!")

        try:
            tweet_json = getTweetJson(username, tweet_id, get_media=True)
        except TweepyException as e:
            logging.error(f"Can't load tweet {username}/status/{tweet_id}: '{e}'")
            reason = e.response.text
            if e.response.status_code == 144:
                reason = "Tweet has been deleted"
            return ET.fromstring(f"<p>Couldn't find tweet <a href='{href}'>'{title or tweet_id}'</a> ({reason})</p>"), m.start(0), index

        except:
            logging.error("Can't load tweet " + tweet_id, exc_info=True)
            return ET.fromstring(f"<p>ERROR! Can't load tweet <a href='{href}'>'{title}'</a></p>"), m.start(0), index

        try:
            # Legacy support:
            tweet_json['entities'] = tweet_json.get('entities', {})
            tweet_json['full_text'] = tweet_json.get('full_text', tweet_json.get('text'))
            tweet_json['extended_entities'] = tweet_json.get('extended_entities', {})
            tweet_json['user'] = tweet_json.get('user', {})
            tweet_json['user']['screen_name'] = tweet_json['user'].get('screen_name', 'unknown')

        except:
            logging.error("Can't load tweet " + tweet_id, exc_info=True)
            return ET.fromstring(f"<p>ERROR! Can't load tweet <a href='{href}'>'{title}'</a></p>"), m.start(0), index

        string = tweet_id  # For error case only
        extra_attrs = " ".join([
            f'data-{k}="{v}"' for k, v in
            dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(href).query)).items()
        ])
        try:
            string = TWEET_TEMPLATE.render(md_title=title, extra_attrs=extra_attrs, **tweet_json)
            # return ET.fromstring(string), m.start(0), m.end(0)
            return self.md.htmlStash.store(string), m.start(0), index
        except ET.ParseError as e:
            logging.error(string, exc_info=True)
            raise e

    def getLink(self, data, index):
        href, title, index, handled = super().getLink(data, index)
        if handled:
            match = re.match(TWEETLINK_RE, href)
            if match:
                http, www, username, tweet_id = match.groups()
                return href, username, tweet_id, title, index, handled
        return None, None, None, None, None, None


class PelicanTweetEmbedMdExtension(markdown.Extension):
    def extendMarkdown(self, md):
        # logging.debug("Registering tweet_embed markdown pattern")
        md.inlinePatterns.register(TweetEmbedProcessor(markdown.inlinepatterns.IMAGE_LINK_RE, md), 'tweet_embed', 200)

def urlretrieve(src, dest):
    try:
        return urllib.request.urlretrieve(src, dest)
    except Exception as e:
        try:
            return urllib.request.urlretrieve('https://web.archive.org/web/0im_/' + src, dest)
        except:
            raise e

def getTweetJson(username, tweet_id, get_media=False):
    tweet_id = str(tweet_id)
    dest_dir = os.path.join("tweets", username)
    dest_path = os.path.join(dest_dir, f"s{tweet_id}.json")

    if not os.path.isfile(dest_path):
        old_path = os.path.join("tweets", username[:3].lower(), username, f"s{tweet_id}.json")
        loose_path = os.path.join("tweets", f"{tweet_id}.json")
        if os.path.isfile(old_path):
            logging.info("Found old-style tweet data path " + old_path)
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(old_path, dest_path)
        elif os.path.isfile(loose_path):
            logging.info("Found loose tweet data path " + loose_path)
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(loose_path, dest_path)
        else:
            pass
            # Handled in below try
            # raise FileNotFoundError(f"{username}, {tweet_id}")

    try:
        with open(dest_path, "r") as fp:
            json_obj = json.load(fp)
            # logging.debug("Found saved tweet data for " + tweet_id)

            # Temporary: Passthrough to RT
            startswith = json_obj.get("full_text", json_obj.get("text", '')).startswith("RT @")
            if startswith and (rt_obj := json_obj.get("retweeted_status")):
                rt_obj['retweeted_by'] = json_obj.get('user', {})
                json_obj = rt_obj

            if TWEET_DOWNLOAD_IMAGES and TWEET_DOWNLOAD_IMAGE_BACKLOG and json_obj.get("entities", {}).get("media"):
                try:
                    for media in json_obj["entities"]["media"]:
                        src = get_real_src_url(media)
                        __, mname = os.path.split(src)
                        media_dest_path = os.path.join(dest_dir, f"s{json_obj['id']}-{mname}")
                        if not os.path.isfile(media_dest_path):
                            print("DOWN", src, '->', media_dest_path)
                            urlretrieve(src, media_dest_path)
                        # else:
                        #     print("SKIP", src, '->', media_dest_path)

                except Exception as e:
                    print(f"Media error {json_obj['id']!r}: {e}")
                    open(media_dest_path, 'wb') # touch file

            return json_obj

    except FileNotFoundError:
        # No file yet
        # logging.warning("Not seeing cached tweet for id " + tweet_id)
        # raise

        try:
            if not api:
                raise FileNotFoundError("API configuration must be passed in to use network functionality")

            status = api.get_status(tweet_id, tweet_mode='extended')
            logging.info("Downloaded new tweet for id " + tweet_id)

            os.makedirs(dest_dir, exist_ok=True)
            with open(dest_path, "w") as fp:
                json.dump(status._json, fp, indent=2)

            if TWEET_DOWNLOAD_IMAGES and get_media and status.entities.get("media"):
                try:
                    for media in status._json["entities"]["media"]:
                        src = get_real_src_url(media)
                        __, mname = os.path.split(src)
                        media_dest_path = os.path.join(dest_dir, f"s{status.id}-{mname}")
                        if not os.path.isfile(media_dest_path):
                            urlretrieve(src, media_dest_path)

                except Exception as e:
                    print(f"Media error {status.id!r}: {e}")

            if TWEET_RECURSE_THREADS and status._json.get("in_reply_to_status_id_str"):
                logging.info("Also downloading replied-to tweet " + status._json['in_reply_to_status_id_str'])
                getTweetJson(status._json['in_reply_to_screen_name'], status._json['in_reply_to_status_id_str'])
            
            if TWEET_RECURSE_QRTS and status._json.get("quoted_status"):
                logging.info("Also downloading quoted tweet " + status._json.get("quoted_status")['id_str'])
                getTweetJson(status._json.get("quoted_status")['user']['screen_name'], status._json.get("quoted_status")['id'])

            return status._json

        except (TweepyException, AssertionError) as e:
            # logging.error(f"Can't load tweet {username}/{tweet_id}: '{e}'")
            if TWEET_FALLBACK_ON:
                try:
                    return getTweetJsonFallback(username, tweet_id)
                except FileNotFoundError as e2:
                    logging.error(str(e2), exc_info=False)
                    raise e
            else:
                raise
        except Exception:
            logging.error(f"Can't retrieve tweet with id '{tweet_id}'", exc_info=1)
            raise

def getTweetJsonFallback(username, tweet_id, **kwargs):
    tweet_id = str(tweet_id)
    dest_dir = os.path.join("tweets", username)
    dest_path = os.path.join(dest_dir, f"s{tweet_id}.json")

    try:
        src_path = TWEET_FALLBACK_DICT[tweet_id]
    except KeyError:
        raise FileNotFoundError(f"'{tweet_id}' not in fallback dictionary")

    # If we're at the fallback, there shouldn't be a normal file.
    assert not os.path.isfile(dest_path)

    # old_path = os.path.join("tweets", username[:3].lower(), username, f"s{tweet_id}.json")
    if os.path.isfile(src_path):
        logging.info("Found fallback tweet data path '%s', copying to '%s'", src_path, dest_path)
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(src_path, dest_path)
    else:
        raise FileNotFoundError(f"'{tweet_id}' in fallback dictionary but not on disk")

    return getTweetJson(username, tweet_id, **kwargs)


def register():
    """Plugin registration"""
    signals.initialized.connect(pelican_init)

TWEET_EMBED_TEMPLATE = env.from_string("""{{ user.screen_name }}: {{ full_text|e|replace("\n\n", " - ")|replace("\n", " - ") }}](https://twitter.com/{{ user.screen_name }}/status/{{ id }}""")

def replaceBlanksInFile(filepath, replace_only_uncaptioned=True):
    with open(filepath, "r", encoding="utf-8") as fp:
        body = fp.read()

    dirty = False
    for match in re.finditer(TWEETEMBED_NOTITLE_RE, body):
        force_uncaptioned_prefix = "![" if replace_only_uncaptioned else ""
        try:
            http, www, username, tweet_id = match.groups()
            rendered = TWEET_EMBED_TEMPLATE.render(**getTweetJson(username, tweet_id, get_media=True))
            whole_md_object = force_uncaptioned_prefix + "](" + match.group(0)

            # logging.warning(f"{whole_md_object!r} -> {rendered!r}")
            body = body.replace(whole_md_object, force_uncaptioned_prefix + rendered)
            dirty = True
        except FileNotFoundError:
            logging.warning(f"No saved info for tweet {match!r} {(username, tweet_id)!r}", exc_info=False)
        except Exception as e:
            logging.error(e)
            logging.warning(f"{filepath}: Couldn't get tweet \n\t{match.group()}")
    
    if dirty:
        with open(filepath, "w", encoding="utf-8") as fp:
            fp.write(body)
    

if __name__ == "__main__":
    import sys

    tweepy_config_path = os.path.abspath("./tweepy_config.py")
    sys.path.insert(0, os.path.dirname(tweepy_config_path))
    try:
        import tweepy_config
        auth = tweepy.OAuthHandler(tweepy_config.TWEEPY_CONSUMER_KEY, tweepy_config.TWEEPY_CONSUMER_SECRET)
        auth.set_access_token(tweepy_config.TWEEPY_ACCESS_TOKEN, tweepy_config.TWEEPY_ACCESS_TOKEN_SECRET)
        api = tweepy.API(auth, wait_on_rate_limit=True)
        logging.info("Logged in to twitter via Tweepy")

    except ImportError:
        logging.warning("Couldn't import , won't have internet functionality!", exc_info=True)
    except:
        import traceback
        traceback.print_exc()
        logging.info("Tweepy not configured; using local tweets only.")

    for globstr in sys.argv[1:]:
        for filepath in glob.glob(globstr, recursive=True):
            replaceBlanksInFile(filepath)
