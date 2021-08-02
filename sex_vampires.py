# -*- coding: utf-8 -*-
"""
Better tipue search

"""

import os.path
import re
import json
from bs4 import BeautifulSoup
from codecs import open

try:
    from urlparse import urljoin
except ImportError:
    from urllib.parse import urljoin

from pelican import signals
from pelican.generators import CachingGenerator

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

class TipuesearchContentGenerator(CachingGenerator):

    def __init__(self, context, settings, path, theme, output_path, *null):

        self.output_path = output_path
        self.context = context
        self.siteurl = settings.get('SITEURL')
        self.relative_urls = settings.get('RELATIVE_URLS')
        self.tpages = settings.get('TEMPLATE_PAGES')
        self.output_path = output_path
        self.json_nodes = []

    def generate_output(self, writer):
        # The primary function that gets called. 

        # Our output is the tipuesearch content body.
        path = os.path.join(self.output_path, 'tipuesearch_content.js')

        # Gather all the content we can
        pages = self.context['pages'] + self.context['articles']
        for article in self.context['articles']:
            pages += article.translations

        # Process raw pages
        for srclink in self.context.get('RAW_PAGES_TO_INDEX', []):
            self.json_nodes.append(self.nodeFromRawPage(srclink))

        # Process template pages
        for srclink in self.tpages:
            self.json_nodes.append(self.nodeFromRawPage(self.tpages[srclink]))

        # Process non-template pages
        for page in pages:
            self.json_nodes.append(self.nodeFromPage(page))

        # Make variable object
        data = json.dumps({'pages': self.json_nodes}, separators=(',', ':'), ensure_ascii=False, indent=1)

        # Dump variable to js file
        root_node_js = f'var tipuesearch = {data};'
        with open(path, 'w', encoding='utf-8') as fd:
            fd.write(root_node_js)

    def nodeFromPage(self, page):
        # Takes a page or article and creates a search node

        # Don't index drafts or other non-published documents
        if getattr(page, 'status', 'published') != 'published':
            return

        soup_title = BeautifulSoup(page.title, 'html.parser')
        page_title = unTypography(soup_title.get_text(' ', strip=True))

        soup_text = BeautifulSoup(page._content, 'html.parser')
        page_text = unTypography(soup_text.get_text(' ', strip=True))
        # page_text = ' '.join(page_text.split())

        page_category = page.category.name if getattr(page, 'category', 'None') != 'None' else ''

        page_url = '.'
        if page.url:
            page_url = page.url if self.relative_urls else (self.siteurl + '/' + page.url)

        node = {
            'title': page_title,
            'text': page_text,
            'tags': page_category,
            'url': page_url,
            'loc': page_url
        }  

        return node

    def nodeFromRawPage(self, srclink):
        # Takes a url to a template page and creates a search node

        srcfile = open(os.path.join(self.output_path, srclink), encoding='utf-8')
        soup = BeautifulSoup(srcfile, 'html.parser')

        # Only printable characters
        while True:
            script = soup.find("script")
            if script:
                script.extract()
            else:
                break

        page_title = unTypography(soup.title.string) if soup.title is not None else ''
        page_text = unTypography(soup.get_text())

        # Should set default category?
        page_category = 'page'
        page_url = urljoin(self.siteurl, srclink)

        node = {
            'title': page_title,
            'text': page_text,
            'tags': page_category,
            'url': page_url
        }

        return node

def get_generators(generators):
    return TipuesearchContentGenerator

def register():
    signals.get_generators.connect(get_generators)
