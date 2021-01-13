# -*- coding: utf-8 -*-
import json
import logging
import markdown
import os
import re
import tweepy
import xml.etree.ElementTree as ET
import html
import shutil

from jinja2 import Environment
# from pelican import generators
from pelican import signals

TWEETEMBED_RE = r"\[\![Tt]weet[^\]]*\]\(.+status\/(\d+).*?\)"
TWEETLINK_RE = r"(https|http)://(www.){0,1}twitter\.com/([^/]+)/status/(\d+).*?"
        
DEBUG = True

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

TWEET_TEMPLATE_STR = """<blockquote class="twitter-tweet" data-lang="en" data-dnt="true" data-nosnippet="true">
    <div class="header">
    {% autoescape true %}
        <a href="https://twitter.com/{{ user.screen_name }}/" title="{{ user.description|replace("\n", " ") }}">
            <img src="{{ user.profile_image_url_https }}"
                onerror="this.onerror=null;this.src=`https://web.archive.org/web/0/${this.src}`;"
            ></img>
            <div class="vertical">
                <span class="name">{{ user.name }}</span>
                <span class="at">@{{ user.screen_name }}</span>
            </div>
        </a>
    {% endautoescape %}
    </div>
    <p>
        {% if in_reply_to_status_id %}
            <span class="replyto">Replying to <a class="prev" href="https://twitter.com/{{in_reply_to_screen_name}}/status/{{ in_reply_to_status_id }}">{{in_reply_to_screen_name}}</a>:</span>
        {% endif %}
        {{ full_text|e|replace("\n", "<br></br>")|tw_stripents(id, entities, extended_entities or {}) }}
    </p>
    <div class="media" style="display: none;">{{ full_text|e|tw_entities(id, entities, extended_entities or {}) }}</div>
    <a href="https://twitter.com/{{ user.screen_name }}/status/{{ id }}" target="_blank">{{ created_at }}</a>
</blockquote>"""

api = None

def tw_entities(text, id, entities, extended_entities):
    entities.update(extended_entities)

    text = ""

    try:

        media = entities.get('media', [])
        media_count = len(media)
        for e in media:
            if e['type'] == "photo":
                src = html.escape(e['media_url_https'])
                repl = f"""<a href="{e['expanded_url']}" target="_blank">
    <img class="img count{media_count}" src="{src}"></img>
</a>"""
            elif e['type'] == "video":
                src = html.escape(e['video_info']['variants'][0]['url'])
                repl = f"""<video src="{src}" controls="true"></video>"""
            elif e['type'] == "animated_gif":
                src = html.escape(e['video_info']['variants'][0]['url'])
                repl = f"""<video src="{src}" loop="true" playsinline="true" controls="true" preload="auto"></video>"""
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
        repl = f"<a href='{src}' target='_blank'>{e['display_url']}</a>"
        if DEBUG:
            ET.fromstring(repl)
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
    consumer_key = pelican_object.settings.get('TWEEPY_CONSUMER_KEY', "")
    consumer_secret = pelican_object.settings.get('TWEEPY_CONSUMER_SECRET', "")
    access_token = pelican_object.settings.get('TWEEPY_ACCESS_TOKEN', "")
    access_token_secret = pelican_object.settings.get('TWEEPY_ACCESS_TOKEN_SECRET', "")

    global api
    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_token_secret)
    api = tweepy.API(auth, wait_on_rate_limit=True, wait_on_rate_limit_notify=True)

    os.makedirs("tweets", exist_ok=True)

    pelican_object.settings['MARKDOWN'].setdefault('extensions', []).append(PelicanTweetEmbedMdExtension())


class TweetEmbedProcessor(markdown.inlinepatterns.LinkInlineProcessor):
    """ Return a img element from the given match. """

    def handleMatch(self, m, data):
        text, index, handled = self.getText(data, m.end(0))
        if not handled:
            return None, None, None

        href, username, tweet_id, title, index, handled = self.getLink(data, index)
        if not handled:
            return None, None, None

        try:
            tweet_json = getTweetJson(username, tweet_id)

            # Legacy support:
            tweet_json['entities'] = tweet_json.get('entities', {})
            tweet_json['full_text'] = tweet_json.get('full_text', tweet_json.get('text'))
            tweet_json['extended_entities'] = tweet_json.get('extended_entities', {})
            tweet_json['user'] = tweet_json.get('user', {})
            tweet_json['user']['screen_name'] = tweet_json['user'].get('screen_name', 'unknown')
        except:
            logging.error("Can't load tweet " + tweet_id, exc_info=True)
            return ET.fromstring(f"<p>ERROR! Can't load tweet <a href='{href}'>'{title}'</a></p>"), m.start(0), index

        try:
            string = TWEET_TEMPLATE.render(**tweet_json)
            return self.md.htmlStash.store(string), m.start(0), index
        except ET.ParseError as e:
            print(string)
            print(TWEET_TEMPLATE)
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
        md.inlinePatterns.register(TweetEmbedProcessor(markdown.inlinepatterns.IMAGE_LINK_RE, md), 'tweet_embed', 200)


def getTweetJson(username, tweet_id):
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
            logging.info("Found saved tweet data for " + tweet_id)

            # Temporary: Passthrough to RT
            startswith = json_obj.get("full_text", json_obj.get("text", '')).startswith("RT @")
            if startswith and (rt_obj := json_obj.get("retweeted_status")):
                return rt_obj
            else:
                return json_obj

    except FileNotFoundError:
        # No file yet
        logging.warning("Not seeing cached tweet for id " + tweet_id)
        # raise

        try:
            status = api.get_status(tweet_id, tweet_mode='extended')
            logging.info("Downloaded new tweet for id " + tweet_id)

            os.makedirs(dest_dir, exist_ok=True)
            with open(dest_path, "w") as fp:
                json.dump(status._json, fp, indent=2)
            return status._json

        except Exception:
            logging.error(f"Can't retrieve tweet with id '{tweet_id}'", exc_info=1)
            raise


def register():
    """Plugin registration"""
    signals.initialized.connect(pelican_init)
