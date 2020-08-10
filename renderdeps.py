# -*- coding: utf8 -*-

import logging
from bs4 import BeautifulSoup
from pelican import signals
from pelican.generators import ArticlesGenerator, PagesGenerator

RENDERDEPS_USE_SOUP_DEFAULT = True

def process_content(article):
    """
    Pelican callback
    """

    if article._content is None:
        logging.warning(f"{article.title} is empty!")
        return

    settings = article.settings
    dependencies = settings.get("RENDER_DEPS", [])
    use_soup = settings.get("RENDERDEPS_USE_SOUP", RENDERDEPS_USE_SOUP_DEFAULT)
    soup = BeautifulSoup(article._content, 'html.parser')

    dirty = False

    for (args, kwargs), dep in dependencies:
        logging.debug(f"Checking for '{args} {kwargs}'")
        if soup.find(*args, **kwargs):
            logging.info("Inserting dependency " + repr(dep))
            if use_soup:
                soup.append(BeautifulSoup(dep, 'html.parser'))
                dirty = True
            else:
                article._content += dep
                # just chuck it in
        else:
            logging.debug("Not found")

    if dirty:
        article._content = soup.prettify()

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
