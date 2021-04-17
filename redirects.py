import os
import logging
from six.moves.urllib.parse import urljoin
import six
from pelican import signals
from pelican.utils import pelican_open

if not six.PY3:
    from codecs import open

logger = logging.getLogger(__name__)
source_files = []
TYPES_TO_PROCESS = ['articles', 'hidden_articles', 'pages', 'drafts']


REDIRECT_TEMPLATE = """
<head>
    <meta http-equiv="refresh" content="0; url=/{url}">
</head>
<body>
<script>
    window.location.href = "/{url}"
</script>
<p>If you are not automatically redirected, <a href="/{url}">click here.</a></p>
</body>
"""


def link_source_files(generator):
    """
    Processes each article/page object and formulates copy from and copy
    to destinations, as well as adding a source file URL as an attribute.
    """
    # Get all attributes from the generator that are articles or pages
    documents = sum([
        getattr(generator, attr, None)
        for attr in TYPES_TO_PROCESS
        if getattr(generator, attr, None)
    ], [])

    autoext_setting = generator.settings.get(
        'SHOW_SOURCE_AUTOEXT', False
    )

    # Work on each item
    for post in documents:
        if 'redirect' in post.metadata:
            try:
                # Get the full path to the original source file
                # post_url = os.path.join(post.settings['OUTPUT_PATH'], post.save_as)

                write_to = os.path.join(post.settings['OUTPUT_PATH'], post.metadata['redirect'])
                redirect_to = post.save_as
                # TODO: If we bounced to C:/ here, error out
            except Exception:
                logger.error("Error processing source file for post", exc_info=True)
                continue

            # Format post source dict & populate
            out = {
                # 'redirect_post_url': post_url,
                'redirect_write_to': write_to,
                'redirect_to': redirect_to
            }

            logger.debug('Will write redirect at %s to url %s', write_to, redirect_to)
            source_files.append(out)


def _copy_from_to(from_file, to_file):
    """
    A very rough and ready copy from / to function.
    """


def write_source_files(*args, **kwargs):
    """
    Called by the `page_writer_finalized` signal to process source files.
    """
    for source in source_files:
        # TODO: If write_to is a file, skip the directory bits
        to_dir = source['redirect_write_to']
        os.makedirs(to_dir, exist_ok=True)
        encoding = 'utf-8'
        with open(os.path.join(to_dir, "index.html"), 'w', encoding=encoding) as text_out:
            text_out.write(REDIRECT_TEMPLATE.format(url=source['redirect_to']))
            logger.info('Writing %s', to_dir)


def register():
    """
    Calls the shots, based on signals
    """
    signals.article_generator_finalized.connect(link_source_files)
    signals.page_generator_finalized.connect(link_source_files)
    signals.page_writer_finalized.connect(write_source_files)
