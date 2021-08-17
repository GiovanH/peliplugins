# -*- coding: utf-8 -*-

import re
import itertools
from bs4 import BeautifulSoup

import logging
from pelican import signals
from pelican.generators import CachingGenerator

import collections


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


class FullOutlineGenerator(CachingGenerator):

    def __init__(self, context, settings, path, theme, output_path, *null):
        super().__init__(context, settings, path, theme, output_path)

        self.output_path = output_path
        self.context = context
        self.siteurl = settings.get('SITEURL')
        self.relative_urls = settings.get('RELATIVE_URLS')
        self.tpages = settings.get('TEMPLATE_PAGES')
        self.output_path = output_path

        self.json_nodes = []
        self.save_as = "full_outline.html"

    def generate_output(self, writer):
        # Gather all the content we can
        pages = self.context['pages'] + self.context['articles']
        for article in self.context['articles']:
            pages += article.translations

        # Process non-template pages
        for page in pages:
            self.json_nodes.append(self.nodeFromPage(page))

        keyf = lambda p: p['page'].date
        full_outline = itertools.groupby(
            sorted([p for p in self.json_nodes], key=keyf), 
            lambda p: p['page'].category
        )

        writer.write_file(
            name=self.save_as, 
            template=self.get_template("full_outline"),
            context=self.context,
            relative_urls=self.settings['RELATIVE_URLS'],
            full_outline=full_outline
        )

    def nodeFromPage(self, page):
        # Takes a page or article and creates a search node

        # Don't index drafts or other non-published documents
        if getattr(page, 'status', 'published') != 'published':
            return

        def tocFromElement(element, url):
            r = []
            for s in element.findAll('section'):
                h = s.find(re.compile(r"h[1-6]"))
                r.append({
                    "id": s['id'],
                    "title": unTypography(h.text),
                    "children": tocFromElement(s, url),
                    "url": url
                })
            return r

        soup_text = BeautifulSoup(page.content, 'html.parser')

        node = {}
        node['children'] = tocFromElement(soup_text, page.url)
        node['page'] = page
        node['url'] = page.url
        node['title'] = page.title
        return node


def get_generators(generators):
    return FullOutlineGenerator

def register():
    signals.get_generators.connect(get_generators)
