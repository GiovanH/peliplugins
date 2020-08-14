# -*- coding: utf8 -*-
from markdown.extensions import Extension
# import markdown.inlinepatterns as inlinepatterns
# from markdown.inlinepatterns import LinkInlineProcessor
from markdown.inlinepatterns import ImageInlineProcessor
# import xml.etree.ElementTree as etree
from pelican import signals
import logging

# Pattern must not consume characters
ATTACH_IMAGE_RE = r'\!\[(?=[^\]]*?\]\(\./)'

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


class AutoAttachExtension(Extension):

    def extendMarkdown(self, md):
        # inlinePatterns.register(ImageInlineProcessor(Image_RE, md), 'Image', 160)
        md.inlinePatterns.register(AttachImageInlineProcessor(ATTACH_IMAGE_RE, md), 'attachImage', 150 + 1)
        md.inlinePatterns.register(AttachImageInlineProcessor(ATTACH_IMAGE_RE, md), 'attachImage2', 150 - 1)

def pelican_init(pelican_object):
    pelican_object.settings['MARKDOWN'].setdefault('extensions', []).append(AutoAttachExtension())

def register():
    """Plugin registration"""
    signals.initialized.connect(pelican_init)
