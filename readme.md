# Gio's Pelican Plugins

they're all single-files because come *on*

## Markdeep

WIP support for [Markdeep](https://casual-effects.com/markdeep/) documents.

### Usage

Just put markdeep files in your content directory like you would markdown documents. 
Supported extensions for markdeep are `.mdhtml` and `.md.html`, although the second one will not work with pelican until they implement [#2780](https://github.com/getpelican/pelican/issues/2780). **Do** ***not*** **include the markdeep footer!**

There are some cases where Markdeep documents do not render correctly due to bugs in Markdeep itself. These issues have been reported and may be fixed in the future.

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

Embed tweets as images with any label, but a twitter link instead of an image source.

`![dril tweet](https://twitter.com/dril/status/1283532184985329664?s=20)`

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


## Wordcount

Estimates the word count and reading time of articles.

Appends the following attributes to each article:

- `word_count`, which is rounded to the nearest 10 words
- `instance.est_read_time`, the estimated read time in minutes
- `instance.word_count_wpm`, which is the WPM used in the read time calculation.

These attributes are readable by Jinja and can be used in templates.

### Configuration

`WORDCOUNT_WPM` defines the reading speed used for read time calculations. This defaults to `200`.

## Anchorlinks

Anchorlinks is an extremely simple plugin that simply adds the class `.anchorlink` to any anchorlinks (i.e. jumplinks, links to anchors on the page) in the HTML document.

The only configuration is an optional 

Anchorlinks is designed to be used with additional CSS styling to differentiate the anchorlinks from other links.

Anchorlinks will ignore all links with tags in `ANCHORLINKS_IGNORE`, which is `["footnote-ref", "toclink"]` by default.

## Autoattach

Markdown only.

Automatically attaches dot-slash resources (`![](./img.png)`) using native pelican attaching.

This only effects links beginning with `./`.

There are no options to configure.
