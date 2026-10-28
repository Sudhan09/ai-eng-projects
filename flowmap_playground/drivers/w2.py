"""Week 2 (async-batch-fetcher): your command line. It starts its own fake server, on this machine."""

import shlex

from async_batch_fetcher.cli import main


def run_cli(text):
    return main(shlex.split(text))


ENTRIES = {"cli": {"label": "async-batch-fetcher", "hint": "--jobs 5 --fail-every 3", "run": run_cli}}
