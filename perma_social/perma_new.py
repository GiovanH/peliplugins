import dataclasses
import html
import logging
import os
import re
from typing import Callable, Iterable, Optional, Self, Tuple, Union

import bs4
import requests
from .common import PermaSocial, PostReference, WorkResult, env

logging.basicConfig(level=logging.WARNING)

class PermaSocialNew(PermaSocial):
    NOUN_POST = "post"
    LINK_RE = r"(https|http)://(www.){0,1}(?P<user_id>[^/]+)(?P<post_id>[^ )]+)"

    EMBED_TEMPLATE = env.from_string(
        """{{ author.handle }}: {{ record.text|replace("\n\n", " - ")|replace("\n", " - ") }}]"""
        """(https://bsky.app/profile/{{ author.handle }}/post/{{ url_id }}"""  # )
    )

    POST_HTML_TEMPLATE = env.from_string(re.sub(r'\n +', '', """"""))

    def login(self: Self) -> None:
        raise NotImplementedError

    def getPostMedia(self: Self, json_obj) -> Iterable[Tuple[str, Union[str, Callable]]]:
        raise NotImplementedError

    def getPostJsonApi(self: Self, post_reference: PostReference, reason="") -> WorkResult:
        raise NotImplementedError

    JSON_GETTERS = [*PermaSocial.JSON_GETTERS, getPostJsonApi]

    def getRelatedPosts(self, post_json: dict, post_reference: PostReference) -> Iterable[PostReference]:
        raise NotImplementedError
