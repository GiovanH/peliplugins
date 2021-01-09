# -*- coding: utf-8 -*-
import json
import logging
import markdown
import os
import re
import tweepy
import xml.etree.ElementTree as ET
import html

from jinja2 import Environment
# from pelican import generators
from pelican import signals

TWEETEMBED_RE = r"\[\![Tt]weet[^\]]*\]\(.+status\/(\d+).*?\)"
TWEETLINK_RE = r"(https|http)://(www.){0,1}twitter\.com/[^/]+/status/(\d+).*?"
        
DEBUG = True

# TODO: Clear support for *both* standalone and embeds
# TODO: Standard retweets show RT and partial text
# TODO: Replies don't reference the tweet they're replying to

# TWEET_TEMPLATE = Template("""<p><blockquote class="twitter-tweet" data-lang="en" data-dnt="true">
# <p lang="und" dir="ltr">{{ full_text }}</p>
# <span>– {{ user.name }} (@{{ user.screen_name }})</span>
# <a href="https://twitter.com/{{ user.screen_name }}/status/{{ id }}">{{ created_at }}</a></blockquote></p>""")

# Add
# <script async="true" src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>
# to your renderdeps!

TWEET_TEMPLATE_STR = """<blockquote class="twitter-tweet" data-lang="en" data-dnt="true" data-nosnippet="true">
    <div class="header">
        <a href="https://twitter.com/{{ user.screen_name }}/" title="{{ user.description|e }}">
            <img src="{{ user.profile_image_url_https }}"
                onerror="this.onerror=null;this.src=`https://web.archive.org/web/0/${this.src}`;"
            ></img>
            <div class="vertical">
                <span class="name">{{ user.name|e }}</span>
                <span class="at">@{{ user.screen_name }}</span>
            </div>
        </a>
    </div>
    <p lang="und" dir="ltr">{{ full_text|e|tw_stripents(id, entities, extended_entities or {})|replace("\n", "<br></br>") }}</p>
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
                repl = f"""<video src="{src}" loop="true" playsinline="true" preload="auto"></video>"""
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

    for e in entities['urls']:
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

        href, tweet_id, title, index, handled = self.getLink(data, index)
        if not handled:
            return None, None, None

        try:
            tweet_json = getTweetJson(tweet_id)
        except:
            logging.error("Can't load tweet " + tweet_id, exc_info=True)
            return ET.fromstring(f"<p>ERROR! Can't load tweet <a href='{href}'>'{title}'</a></p>"), m.start(0), index

        string = TWEET_TEMPLATE.render(**tweet_json)
        try:
            return ET.fromstring(string), m.start(0), index
        except ET.ParseError as e:
            print(string)
            raise e

    def getLink(self, data, index):
        href, title, index, handled = super().getLink(data, index)
        if handled:
            match = re.match(TWEETLINK_RE, href)
            if match:
                http, www, tweet_id = match.groups()
                return href, tweet_id, title, index, handled
        return None, None, None, None, None

# class PelicanTweetEmbedInlineProcessor(markdown.inlinepatterns.InlineProcessor):
#     """Inline markdown processing that matches mathjax"""

#     def handleMatch(self, match, data):
#         (tweet_id,) = match.groups()
#         index = len(data)
#         logging.warning(repr([match, data]))

class PelicanTweetEmbedMdExtension(markdown.Extension):
    # def extendMarkdown(self, md):
    #     # append to end of inline patterns

    #     # TWEETEMBED_RE = r"\([Tt]weet: .+status\/(\d+).*?\)"
    #     # # TWEETEMBED_RE = r"\[\![Tt]weet\]\(.+status\/(\d+).*?\)"
    #     # # Matches link tweets in the form of [!Tweet](https://twitter.com/gio_ebooks/status/1250287970134810624)
    #     # tweetembedPattern = PelicanTweetEmbedInlineProcessor(TWEETEMBED_RE)
    #     # # tweetembedPattern.md = md
    #     # md.inlinePatterns.register(tweetembedPattern, 'tweetembed', 75)

    #     # Matches link tweets in the form of [!Tweet](https://twitter.com/gio_ebooks/status/1250287970134810624)
    #     tweetembedPattern = PelicanTweetEmbedInlineProcessor(TWEETEMBED_RE)
    #     # tweetembedPattern.md = md
    #     md.inlinePatterns.register(tweetembedPattern, 'tweetembed2', 200)  # Priority must exceed link

    def extendMarkdown(self, md):
        md.inlinePatterns.register(TweetEmbedProcessor(markdown.inlinepatterns.IMAGE_LINK_RE, md), 'tweet_embed', 200)


def getTweetJson(tweet_id):
    tweet_id = str(tweet_id)
    dest_path = os.path.join("tweets", tweet_id + ".json")
    try:
        with open(dest_path, "r") as fp:
            json_obj = json.load(fp)
            logging.info("Found saved tweet data for " + tweet_id)
            return json_obj
    except FileNotFoundError:
        # No file yet
        logging.warning("Not seeing cached tweet for id " + tweet_id)

        try:
            status = api.get_status(tweet_id, tweet_mode='extended')
            logging.info("Downloaded new tweet for id " + tweet_id)

            with open(dest_path, "w") as fp:
                json.dump(status._json, fp, indent=2)
            return status._json
        except Exception:
            logging.error(f"Can't retrieve tweet with id '{tweet_id}'", exc_info=1)
            raise


def register():
    """Plugin registration"""
    signals.initialized.connect(pelican_init)
