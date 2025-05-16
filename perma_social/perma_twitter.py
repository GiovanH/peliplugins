import logging
import json
import urllib
import os
import functools
import typing
import requests
import html
import sys
import re
import bs4
import subprocess  # noqa: S404
import tweepy  # type: ignore[import]
import timeout_decorator  # type: ignore[import]

import xml.etree.ElementTree as ET  # noqa: S405
import gallery_dl  # type: ignore[import]

from .common import PermaSocial, PostReference, WorkResult, env, envUnstrict

logging.basicConfig(level=logging.WARNING)


def tw_entities(text, id, entities, extended_entities) -> str:
    entities.update(extended_entities)

    entity_text: str = ""
    repl: str = ""

    try:

        media = entities.get('media', [])
        media_count = len(media)
        for e in media:
            if e['type'] == "photo":
                repl = f"""<a href="{e.get('expanded_url') or PermaTwitter.getRealSourceUrl(e)}" target="_blank">
    <img class="img count{media_count}" src="{PermaTwitter.getRealSourceUrl(e)}"
         """ + """onerror="(async () => {this.onerror=null;this.src=`https://web.archive.org/web/0/${this.src}`;})();"
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
            entity_text += repl
    except ET.ParseError as e:
        logging.error(repl)
        raise e

    return entity_text

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

def tw_avatar_src(user):
    profile_image_url = user.get('profile_image_url_https')
    return _tw_avatar_src(profile_image_url, user['screen_name'])

@functools.lru_cache()
def _tw_avatar_src(profile_image_url, screen_name):
    # import base64

    # b64_empty = 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=='
    b64_empty = False

    try:
        # profile_image_url = user.get('profile_image_url_https')
        image_id = profile_image_url.split('/')[-1]
        image_path = f"tweets/{screen_name}/savatar-{image_id}"
    except AttributeError:
        return b64_empty

    if os.path.isfile(image_path):
        import base64
        with open(image_path, 'rb') as fp:
            image_data = base64.b64encode(fp.read())
            if not isinstance(image_data, str):
                # Python 3, decode from bytes to string
                assert isinstance(image_data, bytes)
                image_data = image_data.decode()
            data_url = f'data:image/{os.path.splitext(image_id)[1]};base64,' + image_data
        # print(data_url)
        return data_url
        # return '{static}/../../' + image_path  # doesn't attach
        # return '{filename}/../' + image_path  # Unable to find
        # return '{filename}/../../' + image_path  # Unable to find
        # return '{attach}/../../../' + image_path  # Works
    else:
        # print(os.path.dirname(os.path.realpath(__file__)), image_path)
        # print("miss", profile_image_url, os.path.abspath(image_path))
        return profile_image_url
        # return b64_empty

    # try:
    #     with open(image_path, 'rb') as fp:
    #         image_data = base64.b64encode(fp.read())
    #         if not isinstance(image_data, str):
    #             # Python 3, decode from bytes to string
    #             image_data = image_data.decode()
    #         data_url = f'data:image/{os.path.splitext(image_id)[1]};base64,' + image_data
    #     print(data_url)
    #     return data_url
    # except:

    # return 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=='

    # {{ user.profile_image_url_https or 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==' }}


env.filters['tw_entities'] = tw_entities
env.filters['tw_stripents'] = tw_stripents
env.filters['tw_avatar_src'] = tw_avatar_src
envUnstrict.filters['tw_entities'] = tw_entities
envUnstrict.filters['tw_stripents'] = tw_stripents
envUnstrict.filters['tw_avatar_src'] = tw_avatar_src

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
            {% if user|tw_avatar_src %}
            <img src="{{ user|tw_avatar_src }}"
                onerror="// (async () => {this.onerror=null;const newsrc=`https://web.archive.org/web/0/${this.src}`;console.log(this, this.src, newsrc);this.src=newsrc;})();"
            ></img>
            {% endif %}
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
        profile_image_url = json_obj['user']['profile_image_url_https']
        yield (profile_image_url.split('/')[-1], profile_image_url)

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
            debug_items = [*extractor.items()]
        except (StopIteration, KeyError):
            pass

        try:
            extracted = [*extractor.tweets()][0]
        except IndexError:
            logging.error(f"Couldn't get tweets from tweet extractor {extractor!r}")
            logging.warning(debug_items)
            raise

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
            # print(resp.text)
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

