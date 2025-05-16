import dataclasses
import functools
import html
import json
import logging
import netrc
import os
import posixpath
import re
import traceback
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Self, Tuple, Union

import bs4
import requests
import urllib
from .common import PermaSocial, PostReference, WorkResult, env, envUnstrict

logging.basicConfig(level=logging.WARNING)

import chitose  # type: ignore[import]


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

    @property
    def api(self) -> chitose.BskyAgent: # type: ignore
        if self._api is None:
            # traceback.print_stack()
            self.login()

        return self._api

    def login(self, instance="bsky.social") -> None:
        try:
            rc = netrc.netrc()
            (BSKY_USER, _, BSKY_PASSWD) = rc.authenticators(instance)

            self._api = chitose.BskyAgent(service=f'https://{instance}')
            self._api.login(BSKY_USER, BSKY_PASSWD)
            logging.info(f"Logged into {instance} as {BSKY_USER}")
        except Exception:
            traceback.print_exc()
            logging.info(f"API not configured; using local {self.NOUN_POST}s only.")

    BSKY_CACHE: dict[PostReference, Any] = {}

    def getPostMedia(self, json_obj) -> Iterable[Tuple[str, str]]:
        for image_def in json_obj.get('embed', {}).get('images', []):
            src_url = image_def['fullsize']
            name = posixpath.split(src_url)[-1].replace('@', '.')
            name = name.split('?')[0]
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

    bskyTupleToUri_cache: Dict[PostReference, str] = {}

    def bskyPostToRef(self, post: Dict) -> PostReference:
        return self.PostRef(
            user_id=post['author']['handle'],
            post_id=posixpath.split(post['uri'])[-1]
        )

    def bskyEncachenPost(self, post: Dict) -> None:
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

    def getRelatedPosts(self, post_json: dict, post_reference: PostReference) -> Iterable[PostReference]:
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

