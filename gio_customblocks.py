# -*- coding: utf8 -*-
from customblocks.utils import Markdown as cbMarkdown
from customblocks.utils import E as cbE

def cb_aside(ctx, title=None, *args, **kwargs):
    slugargs = ['-'.join(arg.split()) for arg in args]
    return cbE(
        f"aside.cb.{title}",
        {'_class': ' '.join(slugargs)},
        cbE(f"div", {'class': 'aside-header'},
            cbE(f"span", {'class': 'icon'}),
            cbE(f"span", {'class': 'type'}),
        ),
        cbMarkdown(ctx.content, ctx.parser),
        **kwargs
    )

def cb_blockquote(ctx, *args, **kwargs):
    slugargs = ['-'.join(arg.split()) for arg in args]
    return cbE(
        f"blockquote",
        {'class': ' '.join(slugargs)},
        cbMarkdown(ctx.content, ctx.parser),
        **kwargs
    )

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

def cb_imessage(ctx, name=None, image=None, *args, **kwargs):
    slugargs = ['-'.join(arg.split()) for arg in args]
    body_etree = cbE(
        "blockquote",
        {'class': ' '.join(['imessage'] + slugargs)},
        (cbE('div', {'class': 'phhead'},
            (cbE('img', {'src': image}) if image else None),
            (name if name else None)
        ) if image or name else None),
        cbMarkdown(ctx.content, ctx.parser),
        **kwargs
    )
    # l2 = []
    # for author_group in body_etree[0].findall('li'):
    #     for message_elem in author_group[0].findall('li'):
    #         message_elem.set('data-author', author_group.text)
    #         l2.append(message_elem)
    for root in body_etree.findall('ul'):
        for author_group in root.findall('li'):
            author = author_group.text
            lowered = author.lower()
            author_group.set('data-author', lowered)
            if lowered not in ['you', 'them']:
                author_group.insert(0,
                    cbE('span', {'class': 'author'}, author)
                )
            author_group.text = ''

    return body_etree


def cb_discord(ctx, name=None, image=None, *args, **kwargs):
    slugargs = ['-'.join(arg.split()) for arg in args]
    body_etree = cbE(
        "blockquote",
        {'class': ' '.join(['discord'] + slugargs)},
        cbMarkdown(ctx.content, ctx.parser),
        **dict(filter(lambda kv: not any(
            kv[0].startswith(pre) for pre in ['color_', 'avatar_']
        ), kwargs.items()))
    )

    for root in body_etree.findall('ul'):
        for author_group in root.findall('li'):
            author_group.set('data-author', author_group.text.lower())
            style = ""
            color = kwargs.get(f'color_{author_group.text}')
            if color:
                style += f"--role-color: {color}; "
            avatar = kwargs.get(f'avatar_{author_group.text}')
            if avatar:
                style += f"--icon: url({avatar}); "
            if style:
                author_group.set('style', style)
    return body_etree

def pelican_init(pelican_object):

    def registerCustomBlock(name, callback):
        pelican_object.settings['MARKDOWN']['extension_configs']['customblocks']['generators'][name] = callback

    registerCustomBlock('aside', cb_aside)
    registerCustomBlock('blockquote', cb_blockquote)
    registerCustomBlock('spoiler', cb_spoiler)
    registerCustomBlock('imessage', cb_imessage)
    registerCustomBlock('discord', cb_discord)

def register():
    """Plugin registration"""
    from pelican import signals
    signals.initialized.connect(pelican_init)
