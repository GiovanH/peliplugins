# -*- coding: utf-8 -*-
"""
Better tipue search

"""

import os.path
import re
import itertools
from bs4 import BeautifulSoup
from codecs import open

try:
    from urlparse import urljoin
except ImportError:
    from urllib.parse import urljoin

import logging
from pelican import signals
from pelican.generators import CachingGenerator


logger = logging.getLogger(__name__)

def unTypography(string):
    ret = string
    # Uncaught whitespace
    ret = re.sub(r"[\n\r]+", "\n", ret)

    # Large replacements
    ret = ret.replace("^", '&#94;')
    ret = ret.replace('&nbsp;', ' ')
    ret = ret.replace("“ ", '"')

    # Group replacements
    ret = re.sub(r"[“”]", '"', ret)
    ret = re.sub(r"[‘’]", "'", ret)

    # Single character replacements
    to = " "
    fr = "¶"
    for (pattern, repl) in [(c, to[i]) for i, c in enumerate(fr)]:
        # ret = re.sub(pattern, repl, ret)
        ret = ret.replace(pattern, repl)
    return ret


class RelatedReadingAggregateGenerator(CachingGenerator):

    def __init__(self, context, settings, path, theme, output_path, *null):
        super().__init__(context, settings, path, theme, output_path)

        self.output_path = output_path
        self.context = context
        self.siteurl = settings.get('SITEURL')
        self.relative_urls = settings.get('RELATIVE_URLS')
        self.tpages = settings.get('TEMPLATE_PAGES')
        self.output_path = output_path

        self.json_nodes = []
        self.save_as = "related_reading.html"

    def generate_output(self, writer):
        # The primary function that gets called. 

        # Gather all the content we can
        pages = self.context['pages'] + self.context['articles']
        for article in self.context['articles']:
            pages += article.translations

        # Process template pages
        for srclink in self.tpages:
            self.json_nodes.append(self.nodeFromTPage(srclink))

        # Process non-template pages
        for page in pages:
            self.json_nodes.append(self.nodeFromPage(page))

        keyf = lambda p: p['category']
        related_reading = itertools.groupby(
            sorted([p for p in self.json_nodes if p['links']], key=keyf), 
            keyf
        )

        logger.info(str(related_reading))

        writer.write_file(
            name=self.save_as, 
            template=self.get_template("relatedreading"),
            context=self.context,
            relative_urls=self.settings['RELATIVE_URLS'],
            related_reading=related_reading
        )

    def nodeFromPage(self, page):
        # Takes a page or article and creates a search node

        # Don't index drafts or other non-published documents
        if getattr(page, 'status', 'published') != 'published':
            return

        soup_title = BeautifulSoup(page.title, 'html.parser')
        page_title = unTypography(soup_title.get_text(' ', strip=True))

        soup_text = BeautifulSoup(page._content, 'html.parser')

        page_links = []
        for anchor in soup_text.find_all("a", class_="related_reading"):
            page_links.append(dict(text=anchor.text, href=anchor.get('href')))

        page_category = page.category.name if getattr(page, 'category', 'None') != 'None' else ''

        page_url = '.'
        if page.url:
            page_url = page.url # if self.relative_urls else (self.siteurl + '/' + page.url)

        node = {
            'title': page_title,
            'category': page_category,
            'url': page_url,
            'links': page_links
        }  

        return node

    def nodeFromTPage(self, srclink):
        # Takes a url to a template page and creates a search node

        srcfile = open(os.path.join(self.output_path, self.tpages[srclink]), encoding='utf-8')
        soup = BeautifulSoup(srcfile, 'html.parser')

        # Only printable characters
        while True:
            script = soup.find("script")
            if script:
                script.extract()
            else:
                break

        page_title = unTypography(soup.title.string) if soup.title is not None else ''
        
        page_links = []
        for anchor in soup.find_all("a", class_="related_reading"):
            page_links.append(dict(text=anchor.text, href=anchor.href))

        # Should set default category?
        page_category = 'page'
        page_url = urljoin(self.siteurl, self.tpages[srclink])

        node = {
            'title': page_title,
            'category': page_category,
            'url': page_url,
            'links': page_links
        }

        return node


def get_generators(generators):
    return RelatedReadingAggregateGenerator

def register():
    signals.get_generators.connect(get_generators)
