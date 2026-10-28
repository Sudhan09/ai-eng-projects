"""A playground driver for the sample project (tests/sample), used by the tool tests."""

import asyncio

import sample_shared
from demo import core


def words(text):  # the driver's own helper: never recorded
    return text.split()


def run_sizes(text):
    for size in core.sizes(words(text)):
        print(size)
    return 0


def run_both(text):
    return asyncio.run(core.both([int(x) for x in words(text)]))


def run_main_late(text):
    from demo.__main__ import main  # imported while recording, like a driver entry importing your __main__
    return main()


def run_summary(text):
    """An entry that returns a dict: its keys become the run's END."""
    return {"sizes": list(core.sizes(words(text))), "item": core.make(text)}


# per Part: the entries that Part has (a later Part can reuse another file's entries)
PARTS = {"1": {"entries": {"shared": {"label": "core.make", "hint": "abc", "run": sample_shared.run_make}}, "scenarios": []}}

ENTRIES = {
    "summary": {"label": "a summary", "hint": "a bb", "run": run_summary},
    "main_late": {"label": "python -m demo", "hint": "", "run": run_main_late},
    "sizes": {"label": "core.sizes", "hint": "a bb ccc", "run": run_sizes},
    "both": {"label": "core.both", "hint": "1 2", "run": run_both},
}
