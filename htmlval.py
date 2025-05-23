# -*- coding: utf8 -*-

import logging
import bs4
from pelican import signals
from pelican.generators import ArticlesGenerator, PagesGenerator, TemplatePagesGenerator

TYPES_TO_PROCESS = [
    "articles", "pages", "drafts",
    "hidden_pages", "hidden_articles", 
    "translations", "hidden_translations", "draft_translations", "drafts_translations"
]

def process_content(instance, generator=None):
    """
    Pelican callback
    """
    if instance._content is None:
        return

    # TODO: This is too slow

    issues = []

    # strainer = bs4.SoupStrainer("a")
    soup_doc = bs4.BeautifulSoup(instance._content, 'html.parser')  # , parse_only=strainer)
    element_ids = {h['id'] for h in soup_doc.findAll(id=True)}

    for anchor in soup_doc.findAll("a", href=True):
        url = anchor['href']

        if url.startswith("#") and url != "#":
            if url[1:] not in element_ids:
                issues.append(f"'{anchor}' backlink has no referent {url[1:]!r} in {sorted(element_ids)!r}")

    # Hash text isn't respected by first child, so this catches inline links too.
    # for anchor in soup_doc.select("blockquote > p > a:first-child:not(.cite)"):
    #     issues.append(f"Blockquote begins with plain link, probably meant to be a citation: {anchor}")

    if instance.status != "draft" and not isinstance(generator, PagesGenerator):
        if instance.summary:
            SUMMARY_MAX_LENGTH = instance.settings.get('SUMMARY_MAX_LENGTH')

            summary_soup = bs4.BeautifulSoup(instance.summary, 'html.parser')
            summary_length = len(summary_soup.text)
            if SUMMARY_MAX_LENGTH and summary_length > SUMMARY_MAX_LENGTH:
                if instance.content != instance.summary:
                    issues.append(f"Summary length is {summary_length}/{SUMMARY_MAX_LENGTH}")
                    # issues.append(f"{instance.summary[:200]} ... {instance.summary[-200:]}")
                else:
                    issues.append(f"Unsummarized article length is {summary_length}/{SUMMARY_MAX_LENGTH}")
                    if instance.has_summary:
                        issues.append("Article incorrectly has 'has_summary' set to True!")

        else:
            issues.append("Missing summary")
        
    if issues:
        logging.error(f"HTML validation errors in {instance.relative_source_path}:" + "\n" + "\n".join(issues))


def all_generators_finalized(generators):
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

def article_writer_finalized(generator, writer):
    # Process the articles and pages

    documents = sum([
        getattr(generator, attr, None)
        for attr in TYPES_TO_PROCESS
        if getattr(generator, attr, None)
    ], [])
    for document in documents:
        process_content(document, generator)


def register():
    """
    Part of Pelican API
    """
    # signals.content_object_init.connect(content_object_init)

    # signals.all_generators_finalized.connect(all_generators_finalized)
    signals.article_writer_finalized.connect(article_writer_finalized)
    signals.page_writer_finalized.connect(article_writer_finalized)

    # logging.info("Register")
    # signals.article_generator_write_article.connect(
    #     lambda gen, content: process_content(content, gen)
    # )
    # signals.page_generator_write_page.connect(
    #     lambda gen, content: process_content(content, gen)
    # )
