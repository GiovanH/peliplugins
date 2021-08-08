import logging
from pelican import signals
import bs4
import nltk.tokenize
import collections
import re

logger = logging.getLogger(__name__)

DEFAULT_WPM = 200
WPM = DEFAULT_WPM

INCL_BLOCKQUOTES = False

TextStats = collections.namedtuple("TextStats", ['stcs', 'words', 'syllables'])

# Todo: This needs functionality for filtering out blockquotes.

only_blockquotes = bs4.SoupStrainer(name='blockquote')
no_blockquotes = bs4.SoupStrainer(lambda n, a: n != 'blockquote')

def pelican_init(pelican_object):
    global WPM
    if not pelican_object.settings.get('WORDCOUNT_WPM'):
        logger.warning("No 'WORDCOUNT_WPM' given, using default value %s", DEFAULT_WPM)
    WPM = pelican_object.settings.get('WORDCOUNT_WPM', DEFAULT_WPM)

def getWordCounter(raw_text):
    # Process the text to remove entities
    entities = r'\&\#?.+?;'
    raw_text = re.sub(entities, '', raw_text.replace('&nbsp;', ' '))

    # Process the text to remove punctuation
    drop = r'.,?!@#$%^&*()_+-=\|/[]{}`~:;\'\"‘’—…“”'
    cleaned_text = raw_text.translate(dict((ord(c), u'') for c in drop))

    # Word counter, count
    words = nltk.tokenize.RegexpTokenizer(r'\w+').tokenize(cleaned_text)
    return collections.Counter(words)

def roundCounterToCount(counter):
    count = sum(counter.values())
    count = int(round(count, -1))
    return count

def getRawText(instance):
    soup = bs4.BeautifulSoup(instance._content, 'html.parser')
    bq_text = []
    for bq in soup.find_all("blockquote"):
        if not bq.find("blockquote"):
            # Must not be a root with nested blockquotes inside
            bq_text.append(bq.getText())
            bq.extract()

    return " ".join(bq_text), soup.getText()

def content_object_init(instance):
    """
    Pelican callback
    """
    if instance._content is None:
        return

    bq_text, nbq_text = getRawText(instance)

    stats = {}

    # Use BeautifulSoup to get readable/visible text
    # raw_text = bs4.BeautifulSoup(instance._content, 'html.parser').getText()

    # Calculate basic word stats
    stats['word_count_wpm'] = WPM

    word_counts_bq = getWordCounter(bq_text)
    # stats['bq_text'] = bq_text
    stats['wc_bq'] = roundCounterToCount(word_counts_bq)
    stats['read_mins_bq'] = stats['wc_bq'] // WPM

    word_counts_nbq = getWordCounter(nbq_text)
    # stats['nbq_text'] = nbq_text
    stats['wc_nbq'] = roundCounterToCount(word_counts_nbq)
    stats['read_mins_nbq'] = stats['wc_nbq'] // WPM

    stats['wc'] = stats['wc_bq'] + stats['wc_nbq']
    stats['read_mins'] = stats['read_mins_bq'] + stats['read_mins_nbq']

    stats['word_counts_nbq'] = word_counts_nbq

    # Calculate Flesch-kincaid readbility stats
    # Stats don't care about sentence order so we can just concat the chunks together
    readability_stats = text_stats(bq_text + nbq_text, stats['wc'])
    stats['fi'] = f"{flesch_index(readability_stats):.2f}"
    stats['fk'] = f"{flesch_kincaid_level(readability_stats):.2f}"

    instance.stats = stats


def register():
    """
    Part of Pelican API
    """
    signals.initialized.connect(pelican_init)
    signals.content_object_init.connect(content_object_init)


# All below: readability

def countSyllables(word):
    if len(word) <= 3:
        return 1

    word = re.sub(r"(es|ed|(?<!l)e)$", "", word)
    return len(re.findall(r"[aeiouy]+", word))


def normalizeText(text):
    terminators = ".!?:;"
    term = re.escape(terminators)
    text = re.sub(r"[^%s\sA-Za-z]+" % term, "", text)
    text = re.sub(r"\s*([%s]+\s*)+" % term, ". ", text)
    return re.sub(r"\s+", " ", text)


def text_stats(text, wc):
    text = normalizeText(text)
    stcs = [s.split(" ") for s in text.split(". ")]
    stcs = [s for s in stcs if len(s) >= 2]

    if wc:
        words = wc
    else:
        words = sum(len(s) for s in stcs)

    sbls = sum(countSyllables(w) for s in stcs for w in s)
    return TextStats(len(stcs), words, sbls)

# Adadpted from here: http://acdx.net/calculating-the-flesch-kincaid-level-in-python/
# See here for details: http://en.wikipedia.org/wiki/Flesch%E2%80%93Kincaid_readability_test

def flesch_index(stats):
    if stats.stcs == 0 or stats.words == 0:
        return 0
    return 206.835 - 1.015 * (stats.words / stats.stcs) - 84.6 * (stats.syllables / stats.words)


def flesch_kincaid_level(stats):
    if stats.stcs == 0 or stats.words == 0:
        return 0
    return 0.39 * (stats.words / stats.stcs) + 11.8 * (stats.syllables / stats.words) - 15.59
