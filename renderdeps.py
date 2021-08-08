# -*- coding: utf8 -*-

import logging
from bs4 import BeautifulSoup
from pelican import signals
from pelican.generators import ArticlesGenerator, PagesGenerator, TemplatePagesGenerator

RENDERDEPS_USE_SOUP_DEFAULT = True

def process_content(article, generator=None):
    """
    Pelican callback
    """

    # TODO: This is far too slow.

    if article._content is None:
        logging.warning(f"{article.title} is empty!")
        return

    settings = article.settings
    dependencies = settings.get("RENDER_DEPS", [])
    use_soup = settings.get("RENDERDEPS_USE_SOUP", RENDERDEPS_USE_SOUP_DEFAULT)
    soup = BeautifulSoup(article._content, 'html.parser')

    dirty = False

    for (args, kwargs), dep in dependencies:
        # logging.debug(f"Checking for '{args} {kwargs}'")
        if soup.find(*args, **kwargs):
            logging.info("Inserting dependency " + repr(dep) + " into " + repr(article.slug))
            if use_soup:
                soup.append(BeautifulSoup(dep, 'html.parser'))
                dirty = True
            else:
                article._content += dep
                # just chuck it in
        else:
            # logging.debug("Not found")
            pass

    if dirty:
        article._content = str(soup)
    else:
        # logging.debug("No dependencies in " + repr(article.slug))
        pass
    return


TYPES_TO_PROCESS = [
    "articles", "pages", "drafts",
    "hidden_pages", "hidden_articles", 
    "translations", "hidden_translations", "draft_translations", "drafts_translations"
]


def link_source_files(generator):
    """
    Processes each article/page object and formulates copy from and copy
    to destinations, as well as adding a source file URL as an attribute.
    """
    # Get all attributes from the generator that are articles or pages

def add_deps(generators):
    # Process the articles and pages

    document_generators = [ArticlesGenerator, PagesGenerator, TemplatePagesGenerator]

    for generator in generators:
        if any(isinstance(generator, t) for t in document_generators):
            documents = sum([
                getattr(generator, attr, None)
                for attr in TYPES_TO_PROCESS
                if getattr(generator, attr, None)
            ], [])
            for document in documents:
                process_content(document, generator)
        else:
            logging.debug(f"Renderdeps: Unhandled generator {generator}")


def register():
    signals.all_generators_finalized.connect(add_deps)
