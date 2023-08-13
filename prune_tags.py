# -*- coding: utf-8 -*-

from pelican import signals

import logging
logger = logging.getLogger(__name__)


MIN_TAGS = 2

def run(generators):
    for generator in generators:
        if 'tags' in dir(generator):
            for tag, tagged_articles in [*generator.tags.items()]:
                article_count = len(tagged_articles)
                if article_count < MIN_TAGS and article_count > 0:
                    logger.warning(f"Removing tag {tag} from articles {[i.slug for i in tagged_articles]}")
                    for article in tagged_articles:
                        article.tags.remove(tag)
                    generator.tags.pop(tag)


def register():
    signals.all_generators_finalized.connect(run)
