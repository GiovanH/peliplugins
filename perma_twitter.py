# -*- coding: utf-8 -*-
import ujson as json
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
import requests
import functools

from jinja2 import Environment
# from pelican import generators
from pelican import signals

TWEETLINK_RE = r"(https|http)://(www.){0,1}twitter\.com/([^/]+)/status/(\d+).*?"
TWEETEMBED_NOTITLE_RE = r"(?<=\!\[\]\()" + TWEETLINK_RE + r"(?=\))"

NITTR_HOST = None

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
        <p>{{ full_text|e|replace("\n\n", "</p><p>")|replace("\n", "</p><p>")|tw_stripents(id, entities, extended_entities or {})|replace("&amp;", "&")|replace("&amp;", "&") }}</p>
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
                repl = f"""<a href="{e.get('expanded_url') or get_real_src_url(e)}" target="_blank">
    <img class="img count{media_count}" src="{get_real_src_url(e)}"
         """ + """onerror="(async () => {this.onerror=null;this.src=`https://web.archive.org/web/0/${this.src}`;\})();"
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
        find = e.get('url')
        if find:
            src = html.escape(e.get('expanded_url') or get_real_src_url(e))
            repl = f"<a href='{src}' target='_blank'>{html.escape(e['display_url'])}</a>"
            if DEBUG:
                try:
                    ET.fromstring(repl)
                except ET.ParseError:
                    logging.error(repl, exc_info=True)
            text = text.replace(find, repl)

    for e in entities.get('media', []):
        find = e.get('url')
        if find:
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

    global NITTR_HOST

    TWEET_RECURSE_THREADS = pelican_object.settings.get('TWEET_RECURSE_THREADS', TWEET_RECURSE_THREADS)
    TWEET_RECURSE_QRTS = pelican_object.settings.get('TWEET_RECURSE_QRTS', TWEET_RECURSE_QRTS)
    TWEET_DOWNLOAD_IMAGE_BACKLOG = pelican_object.settings.get('TWEET_DOWNLOAD_IMAGE_BACKLOG', TWEET_DOWNLOAD_IMAGE_BACKLOG)
    TWEET_DOWNLOAD_IMAGES = pelican_object.settings.get('TWEET_DOWNLOAD_IMAGES', TWEET_DOWNLOAD_IMAGES)

    TWEET_FALLBACK_ON = pelican_object.settings.get('TWEET_FALLBACK_ON', TWEET_FALLBACK_ON)
    TWEET_FALLBACK_MATCH = pelican_object.settings.get(
        'TWEET_FALLBACK_MATCH',
        lambda path: re.match(r".*s(\d+)\.json", path).groups(1)
    )

    NITTR_HOST = pelican_object.settings.get('NITTR_HOST', NITTR_HOST)

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
            tweet_json = getTweetJson(username, tweet_id, get_media=True, reason=tweet_id)
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


def ensureTweetComplete(json_obj, path_if_changed=None):
    # global dest_path
    full_text = json_obj.get('full_text') or json_obj.get('text')
    has_note = ('… https://t.co/' in full_text) and (
        any(
            (url['expanded_url'] == f"https://twitter.com/i/web/status/{json_obj['id']}")
            for url in e['urls']
        )
        for e in json_obj['entities']
    )
    if has_note and not json_obj.get('full_text_orig'):
        if NITTR_HOST:
            import bs4
            nittr_url = '/'.join([NITTR_HOST, json_obj['user']['screen_name'], 'status', json_obj['id_str']])
            logging.warning(f"Using nittr to get full_text for {json_obj['id_str']} from {nittr_url=} b/c {json_obj.get('full_text_orig')=}")
            # logging.warning(json_obj)
            resp = requests.get(nittr_url, headers={'User-Agent': 'curl/8.0.1'})
            resp.raise_for_status()
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
        else:
            raise NotImplementedError("Tweet needs note_tweet saved, but no NITTR_HOST set!")
    return json_obj

@functools.lru_cache()
def getTweetJson(username, tweet_id, get_media=False, reason=""):
    # global dest_path
    tweet_id = str(tweet_id)
    dest_dir = os.path.join("tweets", username)
    dest_path = os.path.join(dest_dir, f"s{tweet_id}.json")

    json_obj = None

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

                if TWEET_DOWNLOAD_IMAGES and TWEET_DOWNLOAD_IMAGE_BACKLOG and json_obj.get("entities", {}).get("media"):
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

                return ensureTweetComplete(json_obj, path_if_changed=dest_path)

        except (FileNotFoundError, KeyError, json.decoder.JSONDecodeError):
            # No file yet, or file missing required keys
            # logging.warning("Not seeing cached tweet for id " + tweet_id)
            # raise
            pass

    if not json_obj:
        try:
            json_obj = getTweetJsonTweepy(username, tweet_id, get_media=get_media, reason=reason)
        except (TweepyException, AssertionError) as e:
            logging.error(f"Can't retrieve tweet with id '{tweet_id}'", exc_info=1)
            pass
        except Exception:
            pass

    if not json_obj:
        try:
            # print("Fetching nittr", tweet_id)
            (json_obj, bonus_tweets) = getTweetJsonNittr(username, tweet_id)
            for json_obj_ex in bonus_tweets:
                dest_dir_2 = os.path.join("tweets", json_obj_ex['user']['screen_name'])
                dest_path_2 = os.path.join(dest_dir_2, f"s{json_obj_ex['id']}.json")
                os.makedirs(dest_dir_2, exist_ok=True)
                # print("Saving bonus", json_obj_ex['id'])

                with open(dest_path_2, "w") as fp:
                    json.dump(json_obj_ex, fp, indent=2)
        except FileNotFoundError as e2:
            logging.error(e2, exc_info=True)
            pass

    if (not json_obj) and TWEET_FALLBACK_ON:
        try:
            json_obj = getTweetJsonFileFallback(username, tweet_id)
        except FileNotFoundError as e2:
            logging.error(str(e2), exc_info=False)
            pass

    if json_obj:
        os.makedirs(dest_dir, exist_ok=True)

        with open(dest_path, "w") as fp:
            json.dump(json_obj, fp, indent=2)

        if TWEET_RECURSE_THREADS and json_obj.get("in_reply_to_status_id_str"):
            logging.info("Also downloading replied-to tweet " + json_obj['in_reply_to_status_id_str'])
            getTweetJson(json_obj['in_reply_to_screen_name'], json_obj['in_reply_to_status_id_str'], reason="reply")

        if TWEET_RECURSE_QRTS and json_obj.get("quoted_status"):
            logging.info("Also downloading quoted tweet " + json_obj.get("quoted_status")['id_str'])
            getTweetJson(json_obj.get("quoted_status")['user']['screen_name'], json_obj.get("quoted_status")['id'], reason="quoted")

        if TWEET_DOWNLOAD_IMAGES and get_media and json_obj.get("entities", {}).get("media"):
            try:
                for media in json_obj["entities"]["media"]:
                    src = get_real_src_url(media)
                    __, mname = os.path.split(src)
                    media_dest_path = os.path.join(dest_dir, f"s{json_obj['id']}-{mname}")
                    if not os.path.isfile(media_dest_path):
                        urlretrieve(src, media_dest_path)

            except Exception as e:
                print(f"Media error {json_obj['id']!r}: {e}")

        return json_obj
    else:
        raise Exception(f"Can't retrieve tweet with id '{tweet_id}'")

def getTweetJsonNittr(username, tweet_id):
    if NITTR_HOST:
        import bs4
        # import pickle

        nittr_url = '/'.join([NITTR_HOST, username, 'status', tweet_id])

        resp = requests.get(nittr_url, headers={'User-Agent': 'curl/8.0.1'})
        resp.raise_for_status()
        # with open("temp.pickle", 'wb') as fp:
        #     pickle.dump(resp.text, fp)
        soup = bs4.BeautifulSoup(resp.text, features="lxml")

        # with open("temp.pickle", 'rb') as fp:
        #     soup = bs4.BeautifulSoup(pickle.load(fp), features="lxml")

        def getNittrTweetObj(tweet_el):
            # print(tweet_el)
            json_obj = {
                'id': tweet_id,
                'user': {'screen_name': username},
                'entities': {
                    "hashtags": [],
                    "symbols": [],
                    "user_mentions": [],
                    "urls": [],
                    "media": [],
                }
            }

        # try:
            import posixpath
            path_str = urllib.parse.urlparse(tweet_el.select('.tweet-date a')[0]['href']).path

            json_obj['id'] = posixpath.split(path_str)[-1]
            json_obj['user']['screen_name'] = str(tweet_el.select('.tweet-header .username')[0]['title'][1:])
            json_obj['user']['name'] = str(tweet_el.select('.tweet-header .fullname')[0]['title'])
        # except IndexError:
        #     logging.warning("Could not get display name", exc_info=True)

            json_obj['created_at'] = str(tweet_el.select('.tweet-date a[title]')[0]['title'])


        # try:
            json_obj['full_text'] = str(tweet_el.select('.tweet-content.media-body')[0].text)
        # except IndexError:
        #     logging.warning("Tweet did not have note? Check has_note logic")
        #     logging.warning(soup.select('.tweet-content.media-body'))

        # try:
            for media_el in tweet_el.select('.attachments .attachment.image'):
                href = urllib.parse.urljoin(NITTR_HOST, media_el.find('a', class_='still-image')['href'])
                # print(href)
                json_obj['entities']['media'].append({
                    "type": "photo",
                    "expanded_url": href,
                    "media_url": href,
                    "media_url_https": href
                })
        # except IndexError:
        #     logging.error(exc_info=True)

            return json_obj

        json_objs = []

        for tweet_el in soup.select('.main-tweet'):
            json_obj_main = getNittrTweetObj(tweet_el)

        for tweet_el in soup.select('.timeline-item .tweet-body'):
            json_objs.append(getNittrTweetObj(tweet_el))

            # print(json.dumps(json_objs, indent=2))

        return (json_obj_main, json_objs)
    else:
        raise NotImplementedError("Tweet needs note_tweet saved, but no NITTR_HOST set!")

def getTweetJsonTweepy(username, tweet_id, get_media=False, reason=""):
    if not api:
        raise FileNotFoundError("API configuration must be passed in to use network functionality")

    # logging.warning(f"Using twitter to get status for {reason}")
    status = api.get_status(tweet_id, tweet_mode='extended')
    logging.info("Downloaded new tweet for id " + tweet_id)

    json_obj = ensureTweetComplete(status._json)

    return json_obj


def getTweetJsonFileFallback(username, tweet_id, **kwargs):
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
    for match in re.finditer(TWEETEMBED_NOTITLE_RE if replace_only_uncaptioned else TWEETLINK_RE, body):
        force_uncaptioned_prefix = "![" if replace_only_uncaptioned else ""
        try:
            http, www, username, tweet_id = match.groups()
            rendered = TWEET_EMBED_TEMPLATE.render(**getTweetJson(username, tweet_id, get_media=True, reason=match))
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

    # NITTR_HOST already global here
    if hasattr(tweepy_config, 'NITTR_HOST'):
        NITTR_HOST = tweepy_config.NITTR_HOST

    for globstr in sys.argv[1:]:
        for filepath in glob.glob(globstr, recursive=True):
            replaceBlanksInFile(filepath)
