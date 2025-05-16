
from .perma_bluesky import PermaBluesky
from .perma_twitter import PermaTwitter
from .perma_mastodon import PermaMastodon
import sys
import traceback
import glob


def __main__():
    socials = [PermaTwitter(), PermaBluesky(), PermaMastodon()]

    for globstr in sys.argv[1:]:
        for filepath in glob.glob(globstr, recursive=True):
            for social in socials:
                try:
                    social.replaceBlanksInFile(filepath)
                except Exception:
                    traceback.print_exc()
                    continue

if __name__ == '__main__':
    __main__()