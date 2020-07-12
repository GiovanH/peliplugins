from pelican import signals
from pelican.readers import BaseReader
import os

FILE_EXTENSIONS = ['md.html', 'mdhtml']

MARKDEEP_FOOTER = """<!-- Markdeep footer -->
<script>window.markdeepOptions={mode:"html"};</script>
<style class="fallback">pre.markdeep{white-space:pre;font-family:monospace}</style>
<script src="https://casual-effects.com/markdeep/latest/markdeep.min.js"></script>
"""
# <style class="fallback">body{visibility:hidden;white-space:pre;font-family:monospace}</style>
# <script>window.alreadyProcessedMarkdeep||(document.body.style.visibility="visible")</script>

# Create a new reader class, inheriting from the pelican.reader.BaseReader
class MarkdeepReader(BaseReader):
    enabled = True  # Yeah, you probably want that :-)

    # The list of file extensions you want this reader to match with.
    # If multiple readers were to use the same extension, the latest will
    # win (so the one you're defining here, most probably).
    file_extensions = FILE_EXTENSIONS

    # You need to have a read method, which takes a filename and returns
    # some content and the associated metadata.
    def read(self, filename):
        with open(filename, "r", encoding="utf-8") as fp:
            full_body = fp.read()

        __, plainname = os.path.split(filename)

        metadata = {
            'title': plainname,
            'category': 'Dev',
            'date': '2012-12-01'
        }

        parsed_metadata = {
            key: self.process_metadata(key, value)
            for key, value in metadata.items()
        }

        full_body = f'<pre class="markdeep">{full_body}</pre>{MARKDEEP_FOOTER}'

        return full_body, parsed_metadata

def add_reader(readers):
    for fe in FILE_EXTENSIONS:
        readers.reader_classes[fe] = MarkdeepReader

# This is how pelican works.
def register():
    signals.readers_init.connect(add_reader)