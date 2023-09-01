# -*- coding: utf8 -*-

import logging
from bs4 import BeautifulSoup
from pelican import signals
from pelican.generators import ArticlesGenerator, PagesGenerator, TemplatePagesGenerator

import threading
import queue

MAX_THREADS = 1
RENDERDEPS_USE_SOUP_DEFAULT = False

def makeStrmatches(args, kwargs):
    tagmatch = f"<{args[0]} " if len(args) > 0 else ""
    class_args = kwargs.get('class_', [])
    if isinstance(class_args, str):
        class_args = [class_args]
    classmatches = [f'class="{v}"' for v in class_args]
    if classmatches:
        return [
            f"{tagmatch}{c}"
            for c in classmatches
        ]
    else:
        return [tagmatch]

def process_dependencies(article, generator=None):
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

    dirty = False

    for (args, kwargs, *strmatches_), dep in dependencies:
        # logging.debug(f"Checking for '{args} {kwargs}'")

        if use_soup:
            soup = BeautifulSoup(article._content, 'html.parser')
            if match := soup.find(*args, **kwargs):
                logging.info("Inserting dependency " + repr(dep) + " into " + repr(article.slug) + " matching" + repr(match))
                soup.append(BeautifulSoup(dep, 'html.parser'))
                dirty = True
        else:
            strmatches = strmatches_ or makeStrmatches(args, kwargs)
            if any(s in article._content for s in strmatches):
                logging.debug(f"Matched '{strmatches}'")
                article._content += dep
                # just chuck it in

    if use_soup and dirty:
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

    THREADED = MAX_THREADS > 1

    if THREADED:
        q = queue.Queue()

        class Worker(threading.Thread):
            def __init__(self, fn, *args, **kwargs):
                self.fn = fn
                super().__init__(*args, **kwargs)

            def run(self):
                while True:
                    try:
                        work = q.get(timeout=3)  # 3s timeout
                    except queue.Empty:
                        return
                    self.fn(*work)
                    q.task_done()

    document_generators = [ArticlesGenerator, PagesGenerator, TemplatePagesGenerator]

    for generator in generators:
        if any(isinstance(generator, t) for t in document_generators):
            documents = sum([
                getattr(generator, attr, None)
                for attr in TYPES_TO_PROCESS
                if getattr(generator, attr, None)
            ], [])
            for document in documents:
                if THREADED:
                    work = (document, generator)
                    q.put_nowait(work)
                else:
                    process_dependencies(document, generator)
        else:
            logging.debug(f"Renderdeps: Unhandled generator {generator}")

    if THREADED:
        for _ in range(MAX_THREADS):
            Worker(process_dependencies).start()
        q.join()  # blocks until the queue is empty.



def register():
    signals.all_generators_finalized.connect(add_deps)
