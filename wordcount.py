import logging
from pelican import signals
import bs4
# import nltk

logger = logging.getLogger(__name__)

DEFAULT_WPM = 200
WPM = DEFAULT_WPM

def pelican_init(pelican_object):
    global WPM
    if not pelican_object.settings.get('WORDCOUNT_WPM'):
        logger.warning("No 'WORDCOUNT_WPM' given, using default value %s", DEFAULT_WPM)
    WPM = pelican_object.settings.get('WORDCOUNT_WPM', DEFAULT_WPM)

def content_object_init(instance):
    """
    Pelican callback
    """
    if instance._content is None:
        return
    
    post_soup = bs4.BeautifulSoup(instance._content, features="html.parser")
    post_text = post_soup.text
    word_count = len(post_text.split())
    instance.word_count = int(round(word_count, -1))
    instance.word_count_wpm = WPM
    instance.est_read_time = int(round(word_count // WPM)) or "< 1"
    instance.link_count = len(post_soup.findAll("a", href=True))


def register():
    """
    Part of Pelican API
    """
    signals.initialized.connect(pelican_init)
    signals.content_object_init.connect(content_object_init)
