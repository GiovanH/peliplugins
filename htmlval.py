# -*- coding: utf8 -*-

import logging
import bs4
import re
from pelican import signals

def add_class(node, name):
    """
    Add class value to a given tag

    :param node:    HTML tag
    :param name:    class attribute value to add
    """
    node['class'] = node.get('class', []) + [name, ]


def content_object_init(instance):
    """
    Pelican callback
    """
    if instance._content is None:
        return

    issues = []

    soup_doc = bs4.BeautifulSoup(instance._content, 'html.parser')
    element_ids = {h['id'] for h in soup_doc.findAll(id=True)}

    for anchor in soup_doc.findAll("a", href=True):
        url = anchor['href']

        if url.startswith("#"):
            if url[1:] not in element_ids:
                issues.append(f"'{anchor}' backlink has no referent")

    if issues:
        logging.error(f"HTML validation errors in {instance.relative_source_path}:" + "\n" + "\n".join(issues))


def register():
    """
    Part of Pelican API
    """
    signals.content_object_init.connect(content_object_init)
