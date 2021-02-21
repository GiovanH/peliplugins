from codecs import open
import collections
from datetime import datetime
import logging
import os.path
import html
import glob
import json
import calendar

import pelican.generators
from pelican import signals
import pelican.readers

class TwGalleryGenerator(pelican.generators.Generator):
    def __init__(self, context, settings, path, theme, output_path, *null):
        super().__init__(context, settings, path, theme, output_path)
        self.glob = settings.get("TWGALLERY_GLOB")

        self.output_path = output_path
        self.context = context

    def loadTweets(self):
        tweet_paths = glob.glob(self.glob, recursive=True)

        tweets = collections.defaultdict(lambda: collections.defaultdict(list))
        for path in tweet_paths:
            try:
                with open(path, "r") as fd:
                    obj = json.load(fd)
                    dt = datetime.strptime(obj["created_at"], "%a %b %d %H:%M:%S +0000 %Y")
            except:
                logging.error(path, exc_info=True)
                continue

            tweets[dt.year][dt.month].append(obj)

        return tweets

    def generate_output(self, writer):
        MarkdownReader = pelican.readers.MarkdownReader(self.context)

        logging.info("Loading tweets")
        corpus = self.loadTweets()

        in_order_pages = [
            (year, month)
            for year in sorted(corpus)
            for month in sorted(corpus[year])
        ]

        for year in corpus:
            year_dir = os.path.join(self.output_path, "twgallery", f"{year}")
            os.makedirs(year_dir, exist_ok=True)

        prev_page_ref = None
        prev_page_label = "ERROR"
        this_page_ref = None
        this_page_label = "ERROR"
        next_page_ref = None
        next_page_label = "ERROR"

        for i, (year, month) in enumerate(in_order_pages):
            mdpath = os.path.join(self.output_path, "twgallery", f"{year}", f"{month}.md")
            htmlpath = f"twgallery/{year}/{month}.html"
            month_name = calendar.month_name[month]

            # Calculate next label. Our label was the old next label.
            try:
                (nyear, nmonth) = in_order_pages[i + 1]
                nmonth_name = calendar.month_name[nmonth]
                next_page_ref = f"twgallery/{nyear}/{nmonth}.html"
                next_page_label = f"{nmonth_name} {nyear}"
            except IndexError:
                next_page_ref = None
                next_page_label = "ERROR"

            # Write intermediate markdown
            logging.info("writing {0}".format(mdpath))
            with open(mdpath, "w", encoding="utf-8") as fd:
                for tweet in sorted(corpus[year][month], key=lambda t: str(t['id'])):
                    try:
                        screen_name = tweet['user']['screen_name']
                    except KeyError:
                        # Old style imports
                        screen_name = "giovan_h"

                    try:
                        desc = tweet.get('full_text') or tweet.get('text')
                        desc = html.escape(desc).replace("\n", "\\n")

                        fd.write(f"![{desc}](https://twitter.com/{screen_name}/status/{tweet.get('id')})\n")
                    except:
                        logging.error(str(tweet), exc_info=True)
                        continue

            # Process markdown w/ extensions
            content, metadata = MarkdownReader.read(mdpath)

            # Write final html file
            logging.info("writing {0}".format(htmlpath))
            writer.write_file(
                name=htmlpath, 
                template=self.get_template("twgallerypage"),
                context=self.context,
                relative_urls=self.settings['RELATIVE_URLS'],
                content=content,
                year=year,
                month_name=month_name,
                prev_page_ref=prev_page_ref,
                prev_page_label=prev_page_label,
                next_page_ref=next_page_ref,
                next_page_label=next_page_label,
                this_page_ref=this_page_ref,
                this_page_label=this_page_label
            )

            # Shift refs back
            prev_page_ref = this_page_ref
            prev_page_label = this_page_label

            this_page_ref = next_page_ref
            this_page_label = next_page_label

def get_generators(generators):
    return TwGalleryGenerator


def register():
    signals.get_generators.connect(get_generators)
