# Gio's Pelican Plugins

they're all single-files because come *on*

## Markdeep

WIP support for [Markdeep](https://casual-effects.com/markdeep/) documents.

### Usage

Just put markdeep files in your content directory like you would markdown documents. 
Supported extensions for markdeep are `.mdhtml` and `.md.html`, although the second one will not work with pelican until they implement [#2780](https://github.com/getpelican/pelican/issues/2780). **Do** ***not*** **include the markdeep footer!**

## Perma twitter

Markdown only.

Embeds tweets in markdown documents while archiving the original tweet source. 
Requires twitter API credentials for Tweepy.

### Configuration

Add tweepy api credentials somewhere in your pelican.conf file.

```python
TWEEPY_CONSUMER_KEY = ""
TWEEPY_CONSUMER_SECRET = ""
TWEEPY_ACCESS_TOKEN = ""
TWEEPY_ACCESS_TOKEN_SECRET = ""
```

(Import them from another file for an extra layer of security.)

### Usage

Embed tweets as links with the label "!tweet" (case insensitive) like so:

`[!Tweet](https://twitter.com/dril/status/1283532184985329664?s=20)`

## Renderdeps

Instead of including javascript dependencies on every page, use this plugin to insert them only when the page requires them.

### Configuration

This is a fully configurable template system, and no specific scripts are provided out of the box.

Renderdeps takes a single configuration variable that defines its entire behavior:

```python
RENDER_DEPS = [
    (
        (args, kwargs), 
        script_include
    ),
    ...
]
```

It is a list of `((args, kwargs), script_include)` tuples. For each item in the list, `args` and `kwargs` are passed as the `args` and `kwargs` to `bs4.BeautifulSoup.find()`. If bs4 finds any element in the article, page, or draft matching the search pattern, Renderdeps will include the `script_include` string at the end of the document.

Here is a full example configuration:

```python
RENDER_DEPS = [
    (
        (["pre"], {"class_": "markdeep"}), 
        """<script>window.markdeepOptions={mode:"html"};</script>
<style class="fallback">pre.markdeep{white-space:pre;font-family:monospace}</style>
<script src="https://casual-effects.com/markdeep/latest/markdeep.min.js"></script>
"""),
    (
        (["pre"], {"class_": "mermaid"}), 
        '<script src="https://unpkg.com/mermaid@8.4.8/dist/mermaid.min.js"></script>'
    )
]
```

Renderdeps has a second configuration variable, `RENDERDEPS_USE_SOUP`. If `RENDERDEPS_USE_SOUP` is `True`, Renderdeps will use BeautifulSoup to gracefully insert a new element at the end of the element tree. If it is `False`, Renderdeps will simply append the dependency string to the end of the document. By default, this is set to `False` due to compatability issues with Pelican's html stash.

## Sex Vampires

This is an alternative for [tipue_search](https://github.com/getpelican/pelican-plugins/tree/master/tipue_search). It is named after pelican-plugins [#1283](https://github.com/getpelican/pelican-plugins/issues/1283).

It is refactored for ease of use and efficiency, and has some additional tweaks that may make it more suitable for some users, listed here:

- Does not include the content of `<script>` tags, even on template pages

## Spoiler box

Markdown only.

Implements bbcode-style spoiler boxes, which can be used to collapse and expand sections of content.

### Usage

Use the tag surrounding standard markdown.

```markdown
[spoiler]
This is *true* markdown text.

Markdown allows you to be lazy and only put the `>` before the first
line of a hard-wrapped paragraph:

> This is a blockquote with two paragraphs. Lorem ipsum dolor sit amet,
consectetuer adipiscing elit. Aliquam hendrerit mi posuere lectus.
Vestibulum enim wisi, viverra nec, fringilla in, laoreet vitae, risus.
[spoiler]
```

There is an alternate syntax wherein `[spoiler]` takes a "parameter", which is used to style the spoiler box button.

```markdown
[spoiler Content]
Some big images
[spoiler]
```

This will show as "Show Content" and "Hide Content" instead of "Show Spoiler".

Spoiler boxes can be nested arbitrarily.

Spoiler contents are considered an inline part of the parent document, and can contain elements like `[TOC]`. The spoiler box is added at the very end of processing.

Suggested CSS would be something like:

```css
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
```

## Wordcount

Estimates the word count and reading time of articles.

Appends the following attributes to each article:

- `word_count`, which is rounded to the nearest 10 words
- `instance.est_read_time`, the estimated read time in minutes
- `instance.word_count_wpm`, which is the WPM used in the read time calculation.

These attributes are readable by Jinja and can be used in templates.

### Configuration

`WORDCOUNT_WPM` defines the reading speed used for read time calculations. This defaults to `200`.
