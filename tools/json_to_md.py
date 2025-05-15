#!/bin/env -S py -3

import json
import sys
import argparse
import itertools
import textwrap

from datetime import datetime

# from typing import get_origin, get_args, Any
from typing import Optional, Mapping
import functools
import operator

QUIRK_EXTRA_LABELS: bool = False
QUIRK_TRIM: bool = False
QUIRK_NO_REPEAT_CHANNEL: bool = False


def keyfunc_timechangroup(msg) -> tuple:
    return (msg["timestamp"][:10], msg["channel"])


def keyfunc_authorgroup(msg) -> str:
    if msg['type'] == 'RecipientAdd':
        return 'SYS'
    return msg["author"]["id"]


def discordHeaderBlock(message_list) -> str:
    args: list[str] = sorted({
        f'avatar_{author["nickname"]}="{author["avatarUrl"]}"'
        for author in
        (message['author'] for message in message_list)
    })
    return (f"::: discord {' '.join(args)}")


def formatMessageTime(message: dict, fmt: str) -> str:
    iso_timestamp = message['timestamp'][:19] + 'Z'
    dt = datetime.strptime(iso_timestamp, "%Y-%m-%dT%H:%M:%SZ")
    return dt.strftime(fmt)


def formatDocuments(json_docs: list[dict]) -> None:
    channels: Mapping[str, dict] = {
        json_doc['channel']['id']: json_doc['channel']
        for json_doc in json_docs
    }

    all_messages: list[dict] = functools.reduce(operator.iadd, [
        [
            {**m, "channel": json_doc['channel']['id']}
            for m in json_doc['messages']
        ]
        for json_doc in json_docs
    ], [])

    replied_to_ids: list[str] = [
        m["reference"]["messageId"]
        for m in all_messages
        if m['type'] == 'Reply'
    ]
    replied_to_messages: dict[str, dict] = {
        m["id"]: m
        for m in all_messages
        if m['id'] in replied_to_ids
    }

    if QUIRK_NO_REPEAT_CHANNEL:
        print(discordHeaderBlock(all_messages))

    time_grouped_messages: list[list[dict]] = []
    for _, g in itertools.groupby(sorted(all_messages, key=keyfunc_timechangroup), keyfunc_timechangroup):
        time_grouped_messages.append(list(g))

    last_channel = None

    for msg_group_time in time_grouped_messages:
        lines: list[Optional[str]] = []

        time_fmt: str = formatMessageTime(msg_group_time[0], "%B %d, %Y")
        chanstr: str = ""

        this_channel = msg_group_time[0]['channel']
        if len(channels.keys()) > 1 and (this_channel != last_channel):
            if not QUIRK_NO_REPEAT_CHANNEL:
                print(discordHeaderBlock(msg_group_time))
                chanstr = f", {channels[this_channel]['name']}"
        last_channel = this_channel

        lines.append(f'<time timestamp="{msg_group_time[0]["timestamp"]}">{time_fmt}{chanstr}</time>')
        lines.append(None)

        author_grouped_messages: list[list[dict]] = []
        # DON'T SORT
        for _, g in itertools.groupby(msg_group_time, keyfunc_authorgroup):
            author_grouped_messages.append(list(g))

        # print("author_grouped_messages", estimate_type(author_grouped_messages), file=sys.stderr)

        for msg_group_time_author in author_grouped_messages:
            for i, message in enumerate(msg_group_time_author):
                time_fmt_granular: str = formatMessageTime(message, "%I:%M %p")

                if i == 0 or QUIRK_EXTRA_LABELS:
                    if message['type'] == 'RecipientAdd':
                        lines.append(
                            f'- SYS <time datetime="{message["timestamp"]}">{time_fmt_granular}</time>'
                        )
                    else:
                        lines.append(
                            f'- {message["author"]["nickname"]} <time datetime="{message["timestamp"]}">{time_fmt_granular}</time>'
                        )

                lines += messageToLines(message, replied_to_messages=replied_to_messages)
        lines.append('')

        for line in lines:
            # print(line, file=sys.stderr)
            if line is None:
                if QUIRK_TRIM:
                    print()
                    continue
                else:
                    line = ''

            print("    " + line)


def messageToLines(message, replied_to_messages={}) -> list[str]:
    lines = []

    if message['type'] == 'Default' or message['type'] == 'Reply':
        # Posts
        if message['type'] == 'Reply':
            reference = replied_to_messages.get(message["reference"]["messageId"])
            if reference:
                preview = textwrap.shorten(reference['content'], width=120)
            else:
                preview = "???"
            lines.append(
                f'    + > {preview}'
            )

        # Hack: Treat "paragraphs" within message as separate messages
        for separate_message in message['content'].split("\n\n"):
            msg_lines: list[str] = separate_message.split("\n")

            block_lines = []
            block_lines.append("    + " + msg_lines[0])
            block_lines += msg_lines[1:]

            # Special line returns on multiline blocks
            if block_lines != ["    + "]:
                lines += "<br>\n     ".join(block_lines).split("\n")

        if message['attachments'] and len(message['attachments']) > 0:
            for a in message['attachments']:
                lines.append(f'    + ![{a["fileName"]}]({a["url"]})')

    elif message['type'] == "RecipientAdd":
        lines.append(
            f'    + {message["author"]["nickname"]} added {message["mentions"][0]["nickname"]} to the group.'
        )
    else:
        print(f"Unknown message type {message['type']}", file=sys.stderr)
        lines.append(
            f'<!-- { {"author": message["author"]["nickname"], "type": message["type"], "content": message["content"]} } -->'
        )

    return lines


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="()",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('input_files', help="Input json files", nargs='+')

    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()

    documents = []
    for input_path in args.input_files:
        with open(input_path, 'r', encoding='utf-8') as fp:
            documents.append(json.load(fp))

    formatDocuments(documents)
