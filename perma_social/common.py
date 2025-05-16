
import collections
import dataclasses
import json
import logging
import os
import re
import urllib
import xml.etree.ElementTree as ET  # noqa: S405
from typing import Callable, Iterable, List, Mapping, Optional, Self, Tuple, Union

import bs4
import jinja2
import markdown
import markdown.inlinepatterns

env = jinja2.Environment(undefined=jinja2.StrictUndefined)  # noqa: S701
envUnstrict = jinja2.Environment()  # noqa: N816, S701

logging.basicConfig(level=logging.WARNING)


def summarize_html(html_code) -> str:
    # logging.warning(html_code)
    soup = bs4.BeautifulSoup(html_code, features="lxml")
    return soup.text


env.filters['summarize_html'] = summarize_html
envUnstrict.filters['summarize_html'] = summarize_html


def urlretrieve(src: str, dest: str) -> None:
    try:
        urllib_request = urllib.request   # type: ignore[attr-defined]
        opener = urllib_request.build_opener()
        opener.addheaders = [('User-agent', 'curl/8.0.1')]
        urllib_request.install_opener(opener)
        urllib_request.urlretrieve(src, dest)
        # resp = requests.get(src, headers={'User-Agent': 'curl/8.0.1'})

    except Exception as e:
        try:
            logging.error(f"Caught url exception {e}")
            return urllib_request.urlretrieve('https://web.archive.org/web/0im_/' + src, dest)  # type: ignore[return-value]
        except:
            raise e


@dataclasses.dataclass(unsafe_hash=True)
class PostReference():
    user_id: str = dataclasses.field(hash=True)
    post_id: str = dataclasses.field(hash=True)


WorkResult = collections.namedtuple("WorkResult", ["result", "nontrivial"])


class PermaSocial:
    NOUN_POST = "post"
    LINK_RE = r"/(?P<user_id>[^/]+)/post/(?P<post_id>[^ )]+)"

    EMBED_TEMPLATE = env.from_string(
        """{{ user.name }}: {{ text|replace("\n\n", " - ")|replace("\n", " - ") }}]"""
        """(/{{ user.id }}/post/{{ post_id }}"""  # )
    )
    POST_HTML_TEMPLATE = env.from_string(
        """<pre>{{ author.handle }}: {{ record.text|replace("\n\n", " - ")|replace("\n", " - ") }}]"""
        """(https://bsky.app/profile/{{ author.handle }}/post/{{ url_id }}</pre>"""  # )
    )

    SET_ALWAYS_RECURSE = False

    @dataclasses.dataclass(unsafe_hash=True)
    class PostRef(PostReference):
        pass

    def __init__(self) -> None:
        self._api = None
        self.EMBED_NOTITLE_RE = r"(?<=\!\[\]\()" + self.LINK_RE + r"(?=\))"

    @property
    def api(self):
        if self._api is None:
            # traceback.print_stack()
            self.login()

        return self._api

    def login(self):
        raise NotImplementedError

    def getRelatedPosts(self, post_json: dict, post_reference: PostReference) -> Iterable[PostReference]:
        raise NotImplementedError

    @classmethod
    def getPostFilePath(cls, json_obj: dict, post_reference: PostReference, makedirs=True, media_id=None) -> str:  # noqa: ARG003
        # json_obj is unused

        dest_dir = os.path.join("socialposts", f"{cls.NOUN_POST}s", post_reference.user_id)

        if makedirs:
            os.makedirs(dest_dir, exist_ok=True)

        filename = f"s{post_reference.post_id}.json"
        if media_id:
            filename = f"s{post_reference.post_id}-{media_id}".split('?')[0]

        return os.path.join(dest_dir, filename)

    def seasonPostReference(self, json_obj, post_reference: PostReference) -> None:
        # Use json_obj to populate post_reference with any additional useful info
        pass

    def getPostJson(self, post_reference: PostReference, get_media=True, reason="Unknown", _traversed=[]) -> dict:
        # logging.debug(f"Starting lookup of {post_reference} for {reason}")

        if ":" in post_reference.user_id:
            raise NotImplementedError

        last_exception: Exception = NotImplemented
        for getter in self.JSON_GETTERS:
            try:
                (json_obj, did_new_work) = getter(self, post_reference, reason=reason)
                # = (getter.__name__ != self.getPostJsonCached.__name__)

                self.seasonPostReference(json_obj, post_reference)

                if self.SET_ALWAYS_RECURSE or did_new_work:
                    with open(self.getPostFilePath(json_obj, post_reference), "w") as fp:
                        json.dump(json_obj, fp, indent=2)

                    # First run resource gathering, but save this json_obj first.
                    if get_media:
                        self.savePostMedia(json_obj, post_reference)
                    for pr2 in self.getRelatedPosts(json_obj, post_reference):
                        if pr2 not in _traversed:
                            self.getPostJson(
                                pr2,
                                reason=f"related to {post_reference}",
                                _traversed=[*_traversed, post_reference]
                            )
                return json_obj
            except Exception as e:
                last_exception = e
                logging.warning(
                    f"{getter.__name__!s} Failed to lookup {(post_reference)} for {reason}",
                    exc_info=False
                )
        raise last_exception

    def getPostJsonCached(self, post_reference, reason="Unknown") -> WorkResult:
        dest_path = self.getPostFilePath({}, post_reference)
        with open(dest_path, "r", encoding="utf-8", newline='\n') as fp:
            return WorkResult(json.load(fp), nontrivial=False)

    JSON_GETTERS: List[Callable] = [getPostJsonCached]

    def getRealSourceUrl(self, media_obj):
        raise NotImplementedError

    def getPostMedia(self: Self, json_obj) -> Iterable[Tuple[str, Union[str, Callable]]]:
        logging.error(json_obj)
        raise NotImplementedError

    def savePostMedia(self, json_obj, post_reference: PostReference, reason="Unknown") -> None:
        for (mname, src_url) in self.getPostMedia(json_obj):
            media_dest_path: str = self.getPostFilePath(json_obj, post_reference, media_id=mname)
            try:
                if isinstance(src_url, str):
                    if "profile_images" in src_url:
                        media_dest_path = self.getPostFilePath(json_obj, PostReference(post_reference.user_id, 'avatar'), media_id=mname)
                    else:
                        # Already set media_dest_path
                        pass

                    src_url_plain: str = src_url.split('?')[0]
                    if not os.path.isfile(media_dest_path):
                        logging.warning(f"DL {src_url_plain} -> {media_dest_path}")
                        urlretrieve(src_url_plain, media_dest_path)
                elif callable(src_url):
                    src_url(media_dest_path)
                else:
                    raise NotImplementedError(src_url)

            except Exception as e:
                logging.error(f"Media error {post_reference}: {e}")
                open(media_dest_path, 'wb')  # touch file

    def embedprocessor(superself, *args, **kwargs) -> markdown.inlinepatterns.LinkInlineProcessor:  # type: ignore # noqa: N805

        class EmbedProcessor(markdown.inlinepatterns.LinkInlineProcessor):
            """ Return a link element from the given match. """

            def handleMatch(self, m, data):
                title, index, handled = self.getText(data, m.end(0))
                if not handled:
                    return None, None, None

                href, matches, __, index, handled = self.getLink(data, index)
                if not handled:
                    return None, None, None

                post_reference: Optional[PostReference] = None
                try:
                    post_reference = superself.PostRef(**matches)  # type: ignore[arg-type]
                    json_obj = superself.getPostJson(post_reference, get_media=True, reason=repr(m))

                except Exception:
                    logging.error(f"Can't load {superself.NOUN_POST} " + repr(post_reference), exc_info=True)
                    placeholder: ET.Element[str] = ET.fromstring(  # noqa: S314
                        f"<p>ERROR! Can't load {superself.NOUN_POST} <a href='{href}'>'{title}'</a></p>"
                    )
                    return (
                        placeholder,
                        int(m.start(0)),
                        int(index)  # type: ignore
                    )

                string = f"{data=}, {post_reference=}"  # For error case only
                extra_attrs = " ".join([
                    f'data-{k}="{v}"' for k, v in
                    dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(href).query)).items()  # type: ignore[type-var]
                ])
                try:
                    string = superself.POST_HTML_TEMPLATE.render(extra_attrs=extra_attrs, **matches, **json_obj)  # type: ignore[arg-type]
                    # return ET.fromstring(string), m.start(0), m.end(0)
                    return (
                        ET.fromstring(self.md.htmlStash.store(string)),  # noqa: S314
                        int(m.start(0)),
                        int(index)  # type: ignore
                    )
                except Exception as e:
                    logging.error(string, exc_info=True)
                    raise e

            def getLink(self, data: str, index: int) -> Union[Tuple[str, Mapping[str, str], str, int, bool], Tuple[None, None, None, None, None]]:
                href, title, index, handled = super().getLink(data, index)
                if handled:
                    # logging.debug(("saw", href, title, index, handled))
                    # It's an image, but is it a post?
                    match = re.match(superself.LINK_RE, href)
                    if match:
                        # logging.debug(("matched", href, title, index, handled))
                        return href, match.groupdict(), title, index, handled
                return None, None, None, None, None

        return EmbedProcessor(*args, **kwargs)

    def replaceBlanksInFile(self, filepath, replace_only_uncaptioned=True):
        with open(filepath, "r", encoding="utf-8") as fp:
            body = fp.read()

        dirty = False
        match_pattern = self.EMBED_NOTITLE_RE if replace_only_uncaptioned else self.LINK_RE
        for match in re.finditer(match_pattern, body):
            force_uncaptioned_prefix = "![" if replace_only_uncaptioned else ""
            # try:
            matches = match.groupdict()
            post_reference = self.PostRef(**matches)
            try:
                json_obj = self.getPostJson(post_reference, get_media=True, reason=repr(matches))
            except Exception as e:
                logging.error("Could not get json to render embed", exc_info=True)
                continue

            try:
                rendered = force_uncaptioned_prefix + self.EMBED_TEMPLATE.render(**matches, **json_obj)
            except Exception as e:
                logging.error(matches, exc_info=False)
                logging.error(json_obj, exc_info=False)
                raise e

            whole_md_object = force_uncaptioned_prefix + "](" + match.group(0)

            logging.debug(f"{whole_md_object!r} -> {rendered!r}")
            body = body.replace(whole_md_object, rendered)
            dirty = True

        if dirty:
            with open(filepath, "w", encoding="utf-8", newline='\n') as fp:
                fp.write(body)


def bs_htmlize(text, facets):
    paragraphs = "<p>" + text.replace("\n\n", "</p><p>").replace("\n", "</p><p>") + "</p>"

    for facet in (facets or []):
        for feature in facet['features']:
            if feature['$type'] == "app.bsky.richtext.facet#link":
                paragraphs = paragraphs.replace(
                    feature['uri'],
                    f"<a href='{feature['uri']}'>{feature['uri']}</a>"
                )
            elif feature['$type'] == "app.bsky.richtext.facet#mention":
                continue
            elif feature['$type'] == "app.bsky.richtext.facet#tag":
                continue
            else:
                raise NotImplementedError(feature['$type'])
    return paragraphs


env.filters['bs_htmlize'] = bs_htmlize
envUnstrict.filters['bs_htmlize'] = bs_htmlize
