# -*- coding: utf-8 -*-

try:
    from urlparse import urljoin
except ImportError:
    from urllib.parse import urljoin

import logging
from pelican import signals
from pelican.generators import ArticlesGenerator

from functools import partial


logger = logging.getLogger(__name__)

def CRC32data(data):
    """Returns the CRC32 "hash" of some data

    Args:
        data: Binary data

    Returns:
        str: Formated CRC32, as {:08X} formatted.

    """
    from binascii import crc32
    buf = (crc32(data) & 0xFFFFFFFF)
    return "{:08X}".format(buf)

class HashedDraftsArticlesGenerator(ArticlesGenerator):
    def generate_output(self, writer):
        logger.info("Getting drafts from context")
        self.drafts = self.context.get("drafts")

        write = partial(
            writer.write_file,
            relative_urls=self.settings['RELATIVE_URLS']
        )
        self.generate_drafts(write)

    def generate_drafts(self, write):
        """Generate drafts pages."""
        for draft in self.drafts:
            dhash = CRC32data(draft.content.encode('utf-8'))
            save_as = self.settings['DRAFT_SAVE_AS'].format(slug=draft.slug + f"-{dhash}")
            write(save_as, self.get_template(draft.template),
                  self.context, article=draft, category=draft.category,
                  override_output=hasattr(draft, 'override_save_as'),
                  blog=True, all_articles=self.articles, url=draft.url)


def get_generators(generators):
    return HashedDraftsArticlesGenerator


def register():
    signals.get_generators.connect(get_generators)
