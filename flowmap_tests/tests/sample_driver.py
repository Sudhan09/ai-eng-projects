"""A playground driver for the sample project (tests/sample), used by the tool tests."""

import asyncio

from demo import core


def words(text):  # the driver's own helper: never recorded
    return text.split()


def run_sizes(text):
    for size in core.sizes(words(text)):
        print(size)
    return 0


def run_both(text):
    return asyncio.run(core.both([int(x) for x in words(text)]))


ENTRIES = {
    "sizes": {"label": "core.sizes", "hint": "a bb ccc", "run": run_sizes},
    "both": {"label": "core.both", "hint": "1 2", "run": run_both},
}
