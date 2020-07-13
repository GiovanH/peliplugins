# -*- coding: utf-8 -*-
import markdown
from jinja2 import Template
import re

# from pelican import generators
from pelican import signals

"""
Suggested CSS would be something like:

    /* Spoiler tags */
    button.spoiler-button {
        margin-left: auto;
        margin-right: auto;
        display: block;
    }

    .spoiler-wrapper {
        border: dashed gray 1px;
        margin: 32px 0px;
        padding: 1px 35px;
    }
"""

MATCH_RE = r"(\[spoiler( .+?){0,1}\])([\S\s]*?)(\[\/spoiler\])"

SCRIPT_PREREQ = """
<script>
    function loggle(button, hidetext, showtext) {
        table = button.parentNode.children[1];
        console.log(button.parentNode);
        console.log(button.parentNode.children);
        console.log(table);
        if (table.style.display == 'none') {
            // We were hidden, now show.
            table.style.display = 'block';
            button.innerText = hidetext;
        } else {
            table.style.display = 'none';
            button.innerText = showtext;
        }
        return false;
    }
</script>
"""

TEMPLATE_PRE = Template("""<div class="spoiler-wrapper">
    <button type="button" class="spoiler-button" onclick="loggle(this, 'Hide {{ desc }}', 'Show {{ desc }}')">
        Show {{ desc }}
    </button>
    <div class="spoiler-content" style="display: none">
""")
        
TEMPLATE_POST = Template("""    </div>
</div>""")

class PelicanSpoilerMdExtension(markdown.Extension):

    def extendMarkdown(self, md):
        """ Add SpoilerblockPreprocessor to the Markdown instance. """
        # md.registerExtension(self)
        md.preprocessors.register(SpoilerblockPreprocessor(md), 'spoiler_block', 29)  # Must be < 30


class SpoilerblockPreprocessor(markdown.preprocessors.Preprocessor):
    def run(self, lines):
        RE = re.compile(MATCH_RE, re.MULTILINE | re.DOTALL | re.IGNORECASE)
        text = "\n".join(lines)
        inserted_script = False

        while True:
            match = RE.search(text)
            if match:
                before = text[:match.start()]
                after = text[match.end():]

                pretag, desc, content, posttag = match.groups()
                desc = desc[1:] if desc else "Spoiler"

                pre_html = TEMPLATE_PRE.render(desc=desc, content=content)
                post_html = TEMPLATE_POST.render(desc=desc, content=content)
                if not inserted_script:
                    pre_html = SCRIPT_PREREQ + pre_html
                    inserted_script = True

                # These HTML blocks get shelved so that the inner content gets rendered as usual.

                pre_html = self.md.htmlStash.store(pre_html)
                post_html = self.md.htmlStash.store(post_html)

                text = "\n".join([before, pre_html, content, post_html, after])
            else:
                break
        return text.split("\n")

def pelican_init(pelican_object):
    pelican_object.settings['MARKDOWN'].setdefault('extensions', []).append(PelicanSpoilerMdExtension())


def register():
    """Plugin registration"""
    signals.initialized.connect(pelican_init)
