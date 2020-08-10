# -*- coding: utf8 -*-

import logging
import bs4
from pelican import signals
from pelican.generators import ArticlesGenerator, PagesGenerator

IGNORE_VAR_NAME = "ANCHORLINKS_IGNORE"
DEFAULT_IGNORE = ["footnote-ref", "toclink"]

def process_content(article):
    """
    Pelican callback
    """

    if article._content is None:
        logging.warning(f"{article.title} is empty!")
        return

    dirty = False
    settings = article.settings
    ignore_tags = settings.get(IGNORE_VAR_NAME, DEFAULT_IGNORE)
    
    soup_doc = bs4.BeautifulSoup(article._content, 'html.parser')

    for anchor in soup_doc.findAll("a", href=True):
        url = anchor['href']

        if url.startswith("#"):
            tag_class = anchor.get('class', [])
            if not any(c in tag_class for c in ignore_tags):
                anchor['class'] = tag_class + ['anchorlink']
                dirty = True

    if dirty:
        article._content = str(soup_doc)

    return


def add_deps(generators):
    # Process the articles and pages
    for generator in generators:
        if isinstance(generator, ArticlesGenerator):
            for article in generator.articles:
                process_content(article)
            for article in generator.drafts:
                process_content(article)
            for article in generator.translations:
                process_content(article)
            for article in generator.drafts_translations:
                process_content(article)
        elif isinstance(generator, PagesGenerator):
            for page in generator.pages:
                process_content(page)
            for page in generator.hidden_pages:
                process_content(page)
            for page in generator.draft_pages:
                process_content(page)
            for page in generator.translations:
                process_content(page)
            for page in generator.hidden_translations:
                process_content(page)
            for page in generator.draft_translations:
                process_content(page)


def register():
    signals.all_generators_finalized.connect(add_deps)
