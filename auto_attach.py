# -*- coding: utf8 -*-
from markdown.extensions import Extension
# import markdown.inlinepatterns as inlinepatterns
from markdown.inlinepatterns import LinkInlineProcessor
from markdown.inlinepatterns import ImageInlineProcessor
# import xml.etree.ElementTree as etree
from pelican import signals
import logging

# Pattern must not consume characters
ATTACH_IMAGE_RE = r'\!\[(?=[^\]]*?\]\(\./)'
ATTACH_LINK_RE = r'\[(?=[^\]]*?\]\(\./)'

class AttachImageInlineProcessor(ImageInlineProcessor):
    def handleMatch(self, m, data):
        # Process image as usual
        el, start, index = super().handleMatch(m, data)

        # Postprocessing
        if el is not None and el.get("src"):
            el_oldsrc = el.get("src")
            el.set("src", "{attach}" + el_oldsrc)
            logging.debug(f"Coercing src '{el_oldsrc}' to '{el.get('src')}'")

        return el, start, index

class AttachLinkInlineProcessor(LinkInlineProcessor):
    def handleMatch(self, m, data):
        # Process image as usual
        el, start, index = super().handleMatch(m, data)

        # Postprocessing
        if el is not None and el.get("href"):
            el_oldsrc = el.get("href")
            el.set("href", "{attach}" + el_oldsrc)
            logging.debug(f"Coercing href '{el_oldsrc}' to '{el.get('href')}'")

        return el, start, index

class AutoAttachExtension(Extension):
    def extendMarkdown(self, md):
        md.inlinePatterns.register(AttachImageInlineProcessor(ATTACH_IMAGE_RE, md), 'attach_image', 170 + 1)
        md.inlinePatterns.register(AttachLinkInlineProcessor(ATTACH_LINK_RE, md), 'attach_link', 160 + 1)

def pelican_init(pelican_object):
    pelican_object.settings['MARKDOWN'].setdefault('extensions', []).append(AutoAttachExtension())

def register():
    """Plugin registration"""
    signals.initialized.connect(pelican_init)
