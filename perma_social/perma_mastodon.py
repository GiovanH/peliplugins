import dataclasses
import html
import logging
import os
import re
from typing import Iterable, Optional, Self, Tuple

import bs4
import requests
from .common import PermaSocial, PostReference, WorkResult, env

logging.basicConfig(level=logging.WARNING)


class PermaMastodon(PermaSocial):
    NOUN_POST = "toot"
    LINK_RE = r"(https|http)://(?P<instance>[^/]+)/@(?P<user_id>[^/]+)/(?!statuses/)(?P<post_id>[^ )]+)"

    EMBED_TEMPLATE = env.from_string(
        """{{ account.username }}@{{ instance }}: {{ content|summarize_html|e|replace("\n\n", " - ")|replace("\n", " - ") }}]({{ url }}"""  # )
    )

    POST_HTML_TEMPLATE = env.from_string(re.sub(r'\n +', '', """<blockquote class="fediverse-toot" data-lang="en" data-dnt="true" data-nosnippet="true" {{ extra_attrs }}>
    <div class="header">
    {% autoescape true %}
        {% if profile_summary is defined %}
        <a href="{{ account.url }}" title="{{ profile_summary|replace("\n", " ") }}">
        {% else %}
        <a href="{{ account.url }}">
        {% endif %}
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
            <!-- <span class="replyto">Replying to <a class="prev" href="">{{ in_reply_to_account_id }}</a>:</span> -->
            <span class="replyto">Replying:</span>
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
        user_id: Optional[str] = dataclasses.field(default=None)

    def login(self: Self) -> None:
        pass

    def seasonPostReference(self, json_obj, post_reference: PostReference) -> None:  # noqa: PLR6301
        user_id = post_reference.user_id or json_obj['account']['username']
        post_reference.user_id = user_id

    @classmethod
    def getPostFilePath(cls, json_obj, post_reference: PostRef, makedirs=True, media_id=None):  # type: ignore[override]
        user_id = post_reference.user_id or json_obj['account']['username']
        if user_id is None:
            raise NotImplementedError("Post reference must have user set to be saved!")
        # backwash
        post_reference.user_id = user_id

        dest_dir = os.path.join("socialposts", f"{cls.NOUN_POST}s", post_reference.instance, user_id)

        if makedirs:
            os.makedirs(dest_dir, exist_ok=True)

        filename = f"s{post_reference.post_id}.json"
        if media_id:
            filename = f"s{post_reference.post_id}-{media_id}".split('?')[0]

        return os.path.join(dest_dir, filename)

    def getRealSourceUrl(self, media_obj) -> str:  # noqa: PLR6301
        if media_obj['type'] == "image":
            return html.escape(media_obj['url'])
        elif media_obj['type'] == "video":
            return html.escape(media_obj['url'])
        elif media_obj['type'] == "gifv":
            return html.escape(media_obj['url'])
        raise NotImplementedError(media_obj)

    def getPostMedia(self: Self, json_obj) -> Iterable[Tuple[str, str]]:
        try:
            for media in json_obj["media_attachments"]:
                src = self.getRealSourceUrl(media)
                __, mname = os.path.split(src)
                yield (mname, src)
        except KeyError as e:
            logging.error(json_obj, exc_info=False)
            raise e

    def getTootJsonApi(self: Self, post_reference: PostRef, reason="") -> WorkResult:
        try:
            resp = requests.get(f"https://{post_reference.instance}/api/v1/statuses/{post_reference.post_id}")
            status_json = resp.json()
            if status_json.get('error'):
                logging.error(status_json, exc_info=False)
                raise ValueError(status_json.get('error'))
        except requests.exceptions.JSONDecodeError:
            logging.error((resp, resp.url, resp.headers, resp.text), exc_info=False)  # type: ignore
            raise
        logging.warning(f"Downloaded new {self.NOUN_POST} for {post_reference} ({reason})")
        return WorkResult(status_json, nontrivial=True)
        # return status_json

    JSON_GETTERS = [*PermaSocial.JSON_GETTERS, getTootJsonApi]
    # JSON_GETTERS = [getTootJsonApi]

    def getRelatedPosts(self, post_json: dict, post_reference: PostRef) -> Iterable[PostRef]:  # type: ignore[override]
        if parent_id := post_json.get('in_reply_to_id'):
            yield self.PostRef(user_id=None, post_id=parent_id, instance=post_reference.instance)

        # "Quote" support
        body_soup = bs4.BeautifulSoup(post_json['content'], features="lxml")
        for link in body_soup.findAll("a"):
            if match := re.match(self.LINK_RE, link['href']):
                yield self.PostRef(**match.groupdict())

        # raise NotImplementedError
