# -*- coding: utf-8 -*-
import json
import logging
import markdown
import os
# import re
import tweepy
import xml.etree.ElementTree as ET

from jinja2 import Template
# from pelican import generators
from pelican import signals

TWEETEMBED_RE = r"\[\![Tt]weet\]\(.+status\/(\d+).*?\)"
        
TWEET_TEMPLATE = Template("""<div><blockquote class="twitter-tweet" data-lang="en" data-dnt="true">
<p lang="und" dir="ltr">{{ full_text }}</p>
<span>– {{ user.name }} (@{{ user.screen_name }})</span>
<a href="https://twitter.com/{{ user.screen_name }}/status/{{ id }}">{{ created_at }}</a></blockquote>
<script async="true" src="https://platform.twitter.com/widgets.js" charset="utf-8"></script></div>""")

api = None


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


class PelicanTweetEmbedInlineProcessor(markdown.inlinepatterns.Pattern):
    """Inline markdown processing that matches mathjax"""

    def handleMatch(self, match):
        tweet_id = match.groups()[1]
        tweet_json = getTweetJson(tweet_id)

        return ET.fromstring(TWEET_TEMPLATE.render(**tweet_json))

class PelicanTweetEmbedMdExtension(markdown.Extension):
    def extendMarkdown(self, md):
        # append to end of inline patterns

        # TWEETEMBED_RE = r"\([Tt]weet: .+status\/(\d+).*?\)"
        # # TWEETEMBED_RE = r"\[\![Tt]weet\]\(.+status\/(\d+).*?\)"
        # # Matches link tweets in the form of [!Tweet](https://twitter.com/gio_ebooks/status/1250287970134810624)
        # tweetembedPattern = PelicanTweetEmbedInlineProcessor(TWEETEMBED_RE)
        # # tweetembedPattern.md = md
        # md.inlinePatterns.register(tweetembedPattern, 'tweetembed', 75)

        # Matches link tweets in the form of [!Tweet](https://twitter.com/gio_ebooks/status/1250287970134810624)
        tweetembedPattern = PelicanTweetEmbedInlineProcessor(TWEETEMBED_RE)
        # tweetembedPattern.md = md
        md.inlinePatterns.register(tweetembedPattern, 'tweetembed2', 200)  # Priority must exceed link


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
        logging.error("Not seeing cached tweet for id " + tweet_id, exc_info=1)

        status = api.get_status(tweet_id, tweet_mode='extended')
        logging.info("Downloaded new tweet for id " + tweet_id)

        with open(dest_path, "w") as fp:
            json.dump(status._json, fp, indent=2)
        return status._json


def register():
    """Plugin registration"""
    signals.initialized.connect(pelican_init)
