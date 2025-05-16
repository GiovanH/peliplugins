import glob
import sys
import traceback

import markdown
import markdown.inlinepatterns
from pelican import signals  # type: ignore[import]

from .perma_bluesky import PermaBluesky
from .perma_twitter import PermaTwitter
from .perma_mastodon import PermaMastodon

# Can't curry these or the pickler gets mad :(


class PelicanSkeetEmbedMdExtension(markdown.Extension):
    def extendMarkdown(self, md):
        md.inlinePatterns.register(
            PermaBluesky().embedprocessor(markdown.inlinepatterns.IMAGE_LINK_RE, md),
            'skeet_embed',
            200
        )


class PelicanMastoEmbedMdExtension(markdown.Extension):
    def extendMarkdown(self, md):
        md.inlinePatterns.register(
            PermaMastodon().embedprocessor(markdown.inlinepatterns.IMAGE_LINK_RE, md),
            'toot_embed',
            200
        )

class PelicanTweetEmbedMdExtension(markdown.Extension):
    def extendMarkdown(self, md):
        md.inlinePatterns.register(
            PermaTwitter().embedprocessor(markdown.inlinepatterns.IMAGE_LINK_RE, md),
            'tweet_embed',
            200
        )

def pelican_init(pelican_object):
    pelican_object.settings['MARKDOWN'].setdefault('extensions', []) \
        .append(PelicanSkeetEmbedMdExtension())
    pelican_object.settings['MARKDOWN'].setdefault('extensions', []) \
        .append(PelicanMastoEmbedMdExtension())
    pelican_object.settings['MARKDOWN'].setdefault('extensions', []) \
        .append(PelicanTweetEmbedMdExtension())


def register():
    """Plugin registration"""
    signals.initialized.connect(pelican_init)

