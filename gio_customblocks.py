# -*- coding: utf8 -*-
from typing import Callable, Sequence, TypeAlias
from customblocks.utils import Markdown as cbMarkdown
from customblocks.utils import E as cbE
import xml
import xml.etree
import xml.etree.ElementTree  # noqa: S405
import logging


Fragment: TypeAlias = xml.etree.ElementTree.Element
Callback: TypeAlias = Callable[..., Fragment]
defined_custom_blocks: dict[str, Callback] = {}

# Helpers

# Decorator to queue a named callback to be registered
def customblock(name: str) -> Callable:
    def _customblock(callback: Callback) -> Callback:
        defined_custom_blocks[name] = callback
        return callback

    return _customblock


def filter_key_prefixes(prefix_blacklist: Sequence[str], obj: dict) -> dict:
    """
    >>> filter_key_prefixes(['a_'], {'a_b': 1, 'b_c': 2})
    {'b_c': 2}
    """
    filtered = filter(
        lambda kv: not any(
            kv[0].startswith(pre) for pre in prefix_blacklist
        ),
        obj.items()
    )
    return dict(filtered)

# Blocks

@customblock('pre')
def cb_pre(ctx, *args, **kwargs) -> Fragment:
    slugargs = ['-'.join(arg.split()) for arg in args]
    return cbE(
        "pre.pre-wrap",
        {'_class': ' '.join(slugargs)},
        ctx.content,
        **kwargs
    )


@customblock('aside')
def cb_aside(ctx, title=None, *args, **kwargs) -> Fragment:
    slugargs = ['-'.join(arg.split()) for arg in args]
    return cbE(
        f"aside.cb.{title}",
        {'_class': ' '.join(slugargs)},
        cbE(
            "div", {'class': 'aside-header'},
            cbE("span", {'class': 'icon'}),
            cbE("span", {'class': 'type'}),
        ),
        cbMarkdown(ctx.content, ctx.parser),
        **kwargs
    )


@customblock('blockquote')
def cb_blockquote(ctx, *args, **kwargs) -> Fragment:
    slugargs = ['-'.join(arg.split()) for arg in args]
    return cbE(
        "blockquote",
        {'class': ' '.join(slugargs)},
        cbMarkdown(ctx.content, ctx.parser),
        **kwargs
    )


@customblock('spoiler')
def cb_spoiler(ctx, desc=None, *args, **kwargs) -> Fragment:
    slugargs = ['-'.join(arg.split()) for arg in args]
    return cbE(
        "div.spoiler-wrapper", {'_class': ' '.join(slugargs)},
        cbE("button", {
            'type': 'button',
            'class': 'spoiler-button',
            'onclick': "this.setAttribute('open', !(this.getAttribute('open') == 'true'))"
        }, desc),
        cbE(
            "div.spoiler-content",
            cbMarkdown(ctx.content, ctx.parser)
        ),
        **kwargs
    )


@customblock('imessage')
def cb_imessage(ctx, name=None, image=None, *args, **kwargs) -> Fragment:
    slugargs = ['-'.join(arg.split()) for arg in args]
    body_etree = cbE(
        "blockquote",
        {'class': ' '.join(['imessage', *slugargs])},
        (
            cbE(
                'div',
                {'class': 'phhead'},
                (cbE('img', {'src': image}) if image else None),
                (name if name else None)
            )
            if image or name else None
        ),
        cbMarkdown(ctx.content, ctx.parser),
        **kwargs
    )

    for root in body_etree.findall('ul'):
        for author_group in root.findall('li'):
            author = author_group.text
            if not author: raise ValueError("Couldn't parse author group", author_group)  # noqa: E701
            author_key = author
            author_group.set('data-author', author_key)
            if author_key not in {'you', 'them'}:
                author_group.insert(
                    0,
                    cbE('span', {'class': 'author'}, author)
                )
            author_group.text = ''

    return body_etree

def _cssSlug(string) -> str:
    return '-'.join( string.lower().split(' '))

@customblock('discord')
def cb_discord(ctx, *args, **kwargs) -> Fragment:
    slugargs = ['-'.join(arg.split()) for arg in args if arg]
    body_etree: Fragment = cbE(
        "blockquote",
        {'class': ' '.join(['discord', *slugargs])},
        cbMarkdown(ctx.content, ctx.parser),
        **filter_key_prefixes(['color_', 'avatar_'], kwargs)
    )

    avatar_prefix = 'avatar_'
    root_style = '; '.join([
        f"--icon-{_cssSlug(k[len(avatar_prefix):])}: url({v})"
        for (k, v) in kwargs.items()
        if k.startswith(avatar_prefix)
    ])
    if root_style:
        body_etree.set('style', root_style)

    for time_segment in body_etree.findall('ul'):
        for (i, author_group) in enumerate(time_segment.findall('li')):
            try:
                if p := author_group.find('p'):
                    # If starting a new list
                    logging.error(xml.etree.ElementTree.tostring(p))
                    author_group.text = p.text
                    author_group.remove(p)
                if not author_group.text:
                    raise ValueError("Couldn't parse author group", author_group)
                author_name = author_group.text.split("<")[0].strip()

                if author_name == 'SYS':
                    author_group.set('class', 'sys')
                    author_group.text = ''
                else:
                    author_group.set('data-author', author_name)

                style_str: str = ""
                color = kwargs.get(f'color_{author_name}')
                if color:
                    style_str += f"--role-color: {color}; "
                avatar = kwargs.get(f'avatar_{author_name}')
                if avatar:
                    style_str += f"--icon: var(--icon-{_cssSlug(author_name)}); "
                if style_str:
                    author_group.set('style', style_str)
            except Exception:
                logging.error(
                    f"Bad discord input in group {i} of "
                    f"{xml.etree.ElementTree.tostring(author_group)} (body "
                    f"{xml.etree.ElementTree.tostring(author_group)})", exc_info=True)
                raise

    return body_etree


@customblock('askblog')
def cb_askblog(ctx, *args, **kwargs) -> Fragment:
    slugargs = ['-'.join(arg.split()) for arg in args]
    return cbE(
        "div",
        {'class': 'askblog-wrapper'},
        cbE(
            "blockquote",
            {'class': ' '.join(['askblog-question', *slugargs])},
            cbE(
                "div",
                {'class': 'askblog-prefix'},
                cbMarkdown(f"**{kwargs.pop('name', 'Anonymous')}** asked:", ctx.parser),
            ),
            cbMarkdown(ctx.content, ctx.parser),
            cbE(
                "div",
                {'class': 'askblog-arrow'}
            ),
        ),
        cbE(
            "div",
            {'class': 'askblog-avatar'},
            cbE(
                "img",
                {'src': kwargs.pop('avatar', '/theme/blocks/ask_anon.png')}
            ),
        ),
        **kwargs
    )


def pelican_init(pelican_object) -> None:

    def registerCustomBlock(name, callback):
        pelican_object.settings['MARKDOWN']['extension_configs']['customblocks']['generators'][name] = callback

    for (name, callback) in defined_custom_blocks.items():
        registerCustomBlock(name, callback)


def register():
    """Plugin registration"""
    from pelican import signals  # noqa: PLC0415
    signals.initialized.connect(pelican_init)
