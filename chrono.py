# -*- coding: utf-8 -*-

try:
    from urlparse import urljoin
except ImportError:
    from urllib.parse import urljoin

import logging
from pelican import signals
from pelican.generators import ArticlesGenerator, CachingGenerator
from collections import defaultdict

from functools import partial
from operator import attrgetter


logger = logging.getLogger(__name__)


class ChronoArticlesGenerator(ArticlesGenerator):

    # Must inherit from ArticlesGenerator for compatibillity with summary

    def generate_output(self, writer):

        self.articles = self.context.get("articles")

        self.tags = self.context.get("tags")
        self.categories = self.context.get("categories")
        self.authors = self.context.get("authors")

        self.dates = self.context.get("dates")
        self.dates.sort(key=attrgetter('date'),
                        reverse=(not self.context['NEWEST_FIRST_ARCHIVES']))

        write = partial(
            writer.write_file,
            relative_urls=self.settings['RELATIVE_URLS']
        )
        self.generate_tags(write)

    def generate_tags(self, write):
        """Generate Tags pages."""
        tag_template = self.get_template('tag')
        for (tag, articles) in self.tags:
            dates = [article for article in self.dates if article in articles]
            saveas = self.settings['TAG_SAVE_AS_REVERSE'].format(
                slug=tag.slug
            )
            write(saveas, tag_template, self.context, tag=tag,
                  url=tag.url, articles=dates, dates=dates,
                  template_name='tag', blog=True, page_name=tag.page_name,
                  all_articles=self.articles)

    def generate_categories(self, write):
        """Generate category pages."""
        category_template = self.get_template('category')
        for cat, articles in self.categories:
            dates = [article for article in self.dates if article in articles]
            saveas = self.settings['CATEGORY_SAVE_AS_REVERSE'].format(
                slug=cat.slug
            )
            write(saveas, category_template, self.context, url=cat.url,
                  category=cat, articles=articles, dates=dates,
                  template_name='category', blog=True, page_name=cat.page_name,
                  all_articles=self.articles)

    def generate_authors(self, write):
        """Generate Author pages."""
        author_template = self.get_template('author')
        for aut, articles in self.authors:
            dates = [article for article in self.dates if article in articles]
            saveas = self.settings['AUTHOR_SAVE_AS_REVERSE'].format(
                slug=aut.slug
            )
            write(saveas, author_template, self.context,
                  url=aut.url, author=aut, articles=articles, dates=dates,
                  template_name='author', blog=True,
                  page_name=aut.page_name, all_articles=self.articles)


def get_generators(generators):
    return ChronoArticlesGenerator


def register():
    signals.get_generators.connect(get_generators)
