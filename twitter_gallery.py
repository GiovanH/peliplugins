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

#

class TwGalleryGenerator(pelican.generators.Generator):
    def __init__(self, context, settings, path, theme, output_path, *null):
        super().__init__(context, settings, path, theme, output_path)
        glob_setting = settings.get("TWGALLERY_GLOB")

        if isinstance(glob_setting, list):
            self.globs = glob_setting
        else:
            self.globs = [glob_setting]

        self.output_path = output_path
        self.context = context
        self.RAW_PAGES_TO_INDEX = []

    def loadTweets(self):
        tweet_paths = sum((glob.glob(g, recursive=True) for g in self.globs), [])
        seen_tweet_ids = set()

        tweets = collections.defaultdict(lambda: collections.defaultdict(list))
        for path in tweet_paths:
            try:
                with open(path, "r") as fd:
                    obj = json.load(fd)
                    dt = datetime.strptime(obj["created_at"], "%a %b %d %H:%M:%S +0000 %Y")
            except:
                logging.error(path, exc_info=True)
                continue

            if replied_to := obj.get("in_reply_to_status_id"):
                if replied_to not in seen_tweet_ids:
                    tweets[dt.year][dt.month].append({
                        "id": replied_to,
                        "bare_id": True
                    })
                    seen_tweet_ids.add(replied_to)

            if obj.get("id") not in seen_tweet_ids:
                tweets[dt.year][dt.month].append(obj)
                seen_tweet_ids.add(obj.get("id"))

        return tweets

    def generate_output(self, writer):
        MarkdownReader = pelican.readers.MarkdownReader(self.context)

        logging.info("Loading tweets")
        corpus = self.loadTweets()

        year_index = {
            year: corpus[year].keys()
            for year in sorted(corpus)
        }

        htmlpath = os.path.join(self.output_path, "twgallery", "index.html")

        logging.info("writing {0}".format(htmlpath))
        writer.write_file(
            name=htmlpath, 
            template=self.get_template("twgallery_index"),
            context=self.context,
            relative_urls=self.settings['RELATIVE_URLS'],
            calendar=year_index,
            monthnames=calendar.month_name
        )

        in_order_pages = [
            (year, month)
            for year in sorted(corpus)
            for month in sorted(corpus[year])
        ]

        # year_prev_page_ref = None
        # year_prev_page_label = "ERROR"
        # year_this_page_ref = None
        # year_this_page_label = "ERROR"
        # year_next_page_ref = None
        # year_next_page_label = "ERROR"

        for year in corpus:
            print("year", year)
            year_dir = os.path.join(self.output_path, "twgallery", f"{year}")
            os.makedirs(year_dir, exist_ok=True)

            # # Calculate next label. Our label was the old next label.
            # if (year + 1) in corpus:
            #     next_page_ref = f"twgallery/{year}/index.html"
            #     next_page_label = f"{year}"
            # else:
            #     next_page_ref = None
            #     next_page_label = "ERROR"

            # htmlpath = os.path.join(self.output_path, "twgallery", f"{year}", "index.html")

            # logging.info("writing {0}".format(htmlpath))
            # writer.write_file(
            #     name=htmlpath, 
            #     template=self.get_template("twgallery_year"),
            #     context=self.context,
            #     relative_urls=self.settings['RELATIVE_URLS'],
            #     year=year,
            #     months=corpus[year],
            #     monthnames=calendar.month_name,
            #     prev_page_ref=year_prev_page_ref,
            #     prev_page_label=year_prev_page_label,
            #     next_page_ref=year_next_page_ref,
            #     next_page_label=year_next_page_label,
            #     this_page_ref=year_this_page_ref,
            #     this_page_label=year_this_page_label
            # )

            # # Shift refs back
            # year_prev_page_ref = year_this_page_ref
            # year_prev_page_label = year_this_page_label

            # year_this_page_ref = year_next_page_ref
            # year_this_page_label = year_next_page_label

        prev_page_ref = None
        prev_page_label = "ERROR"
        this_page_ref = None
        this_page_label = "ERROR"
        next_page_ref = None
        next_page_label = "ERROR"

        for i, (year, month) in enumerate(in_order_pages):
            print(year, month)
            
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
                    if tweet.get("bare_id"):
                        # Bare ID
                        fd.write(f"![{tweet.get('id')}](https://twitter.com/unknown/status/{tweet.get('id')}) ")
                        continue

                    try:
                        screen_name = tweet['user']['screen_name']
                    except KeyError:
                        # Old style imports
                        screen_name = "giovan_h"

                    try:
                        desc = tweet.get('full_text') or tweet.get('text')
                        desc = html.escape(desc).replace("\n", "\\n").replace("(", "\\(").replace(")", "\\)")

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
                template=self.get_template("twgallery_month"),
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
            self.RAW_PAGES_TO_INDEX.append(htmlpath)

            # Shift refs back
            prev_page_ref = this_page_ref
            prev_page_label = this_page_label

            this_page_ref = next_page_ref
            this_page_label = next_page_label

        self.context['RAW_PAGES_TO_INDEX'] = []
        self._update_context(('RAW_PAGES_TO_INDEX',))

def get_generators(generators):
    return TwGalleryGenerator


def register():
    signals.get_generators.connect(get_generators)
