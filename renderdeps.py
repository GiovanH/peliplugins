# -*- coding: utf8 -*-

import logging
from bs4 import BeautifulSoup
from pelican import signals


def process_content(article):
    """
    Pelican callback
    """
    if article._content is None:
        return

    settings = article.settings
    dependencies = settings.get("RENDER_DEPS", [])
    soup = BeautifulSoup(article._content, 'html.parser')

    dirty = False

    for (args, kwargs), dep in dependencies:
        ident = f"{args} {kwargs}"
        logging.debug(f"Checking for '{ident}'")
        if soup.find(*args, **kwargs):
            soup.append(BeautifulSoup(dep, 'html.parser'))
            dirty = True
            logging.info("Inserting dependency " + repr(dep))
        else:
            logging.debug("Not found")

    if dirty:
        article._content = soup.decode()


def add_deps(generators):
    from pelican.generators import ArticlesGenerator, PagesGenerator
    # Process the articles and pages
    for generator in generators:
        if isinstance(generator, ArticlesGenerator):
            for article in generator.articles:
                process_content(article)
        elif isinstance(generator, PagesGenerator):
            for page in generator.pages:
                process_content(page)


def register():
    signals.all_generators_finalized.connect(add_deps)
