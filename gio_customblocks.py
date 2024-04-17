# -*- coding: utf8 -*-
from customblocks.utils import Markdown as cbMarkdown
from customblocks.utils import E as cbE

defined_custom_blocks = {}

# Helpers

# Decorator to queue a named callback to be registered
def customblock(name):
    def _customblock(callback):
        defined_custom_blocks[name] = callback
        return callback
    return _customblock


def filter_key_prefixes(prefix_blacklist, object):
    """
    >>> filter_key_prefixes(['a_'], {'a_b': 1, 'b_c': 2})
    {'b_c': 2}
    """
    filtered = filter(
        lambda kv: not any(
            kv[0].startswith(pre) for pre in prefix_blacklist
        ),
        object.items()
    )
    return dict(filtered)

# Blocks


@customblock('pre')
def cb_pre(ctx, *args, **kwargs):
    slugargs = ['-'.join(arg.split()) for arg in args]
    return cbE(
        f"pre.pre-wrap",
        {'_class': ' '.join(slugargs)},
        ctx.content,
        **kwargs
    )


@customblock('aside')
def cb_aside(ctx, title=None, *args, **kwargs):
    slugargs = ['-'.join(arg.split()) for arg in args]
    return cbE(
        f"aside.cb.{title}",
        {'_class': ' '.join(slugargs)},
        cbE(
            f"div", {'class': 'aside-header'},
            cbE(f"span", {'class': 'icon'}),
            cbE(f"span", {'class': 'type'}),
        ),
        cbMarkdown(ctx.content, ctx.parser),
        **kwargs
    )


@customblock('blockquote')
def cb_blockquote(ctx, *args, **kwargs):
    slugargs = ['-'.join(arg.split()) for arg in args]
    return cbE(
        f"blockquote",
        {'class': ' '.join(slugargs)},
        cbMarkdown(ctx.content, ctx.parser),
        **kwargs
    )


@customblock('spoiler')
def cb_spoiler(ctx, desc=None, *args, **kwargs):
    slugargs = ['-'.join(arg.split()) for arg in args]
    return cbE(
        f"div.spoiler-wrapper", {'_class': ' '.join(slugargs)},
        cbE(f"button", {
            'type': 'button',
            'class': 'spoiler-button',
            'onclick': f"this.setAttribute('open', !(this.getAttribute('open') == 'true'))"
        }, desc),
        cbE(
            f"div.spoiler-content",
            cbMarkdown(ctx.content, ctx.parser)
        ),
        **kwargs
    )


@customblock('imessage')
def cb_imessage(ctx, name=None, image=None, *args, **kwargs):
    slugargs = ['-'.join(arg.split()) for arg in args]
    body_etree = cbE(
        "blockquote",
        {'class': ' '.join(['imessage'] + slugargs)},
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
            lowered = author.lower()
            author_group.set('data-author', lowered)
            if lowered not in ['you', 'them']:
                author_group.insert(
                    0,
                    cbE('span', {'class': 'author'}, author)
                )
            author_group.text = ''

    return body_etree

@customblock('discord')
def cb_discord(ctx, name=None, image=None, *args, **kwargs):
    slugargs = ['-'.join(arg.split()) for arg in args]
    body_etree = cbE(
        "blockquote",
        {'class': ' '.join(['discord'] + slugargs)},
        cbMarkdown(ctx.content, ctx.parser),
        **filter_key_prefixes(['color_', 'avatar_'], kwargs)
    )

    for root in body_etree.findall('ul'):
        for author_group in root.findall('li'):
            author_group.set('data-author', author_group.text.lower())
            style_str = ""
            color = kwargs.get(f'color_{author_group.text}')
            if color:
                style_str += f"--role-color: {color}; "
            avatar = kwargs.get(f'avatar_{author_group.text}')
            if avatar:
                style_str += f"--icon: url({avatar}); "
            if style_str:
                author_group.set('style', style_str)
    return body_etree


@customblock('askblog')
def cb_askblog(ctx, *args, **kwargs):
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

def pelican_init(pelican_object):

    def registerCustomBlock(name, callback):
        pelican_object.settings['MARKDOWN']['extension_configs']['customblocks']['generators'][name] = callback

    for (name, callback) in defined_custom_blocks.items():
        registerCustomBlock(name, callback)


def register():
    """Plugin registration"""
    from pelican import signals
    signals.initialized.connect(pelican_init)
