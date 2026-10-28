"""Week 2 (async-batch-fetcher): each Part's entry, and suggested inputs that together reach every component.

Input: --jobs N, --fail-every K (every Kth job fails), --delay S, --concurrency C, --timeout S, --strict.
Each entry runs against MockServer, the project's own fake server on this machine.
"""

import asyncio
import shlex
import sys


def settings(text):
    import argparse
    p = argparse.ArgumentParser(prog="playground", add_help=False)
    p.add_argument("--jobs", type=int, default=5)
    p.add_argument("--fail-every", type=int, default=0)
    p.add_argument("--delay", type=float, default=0.05)
    p.add_argument("--concurrency", type=int, default=20)
    p.add_argument("--timeout", type=float, default=1.0)
    p.add_argument("--strict", action="store_true")
    return p.parse_args(shlex.split(text))


def on_server(text, work):
    """work(job ids, port, settings), with MockServer running."""
    from async_batch_fetcher.server import MockServer
    a = settings(text)

    async def go():
        async with MockServer(delay=a.delay, fail_every=a.fail_every) as server:
            return await work(list(range(a.jobs)), server.port, a)

    return asyncio.run(go())


def run_serial(text):
    from async_batch_fetcher.batch import run_serial
    return on_server(text, lambda jobs, port, a: run_serial(jobs, port))


def run_gather(text):
    from async_batch_fetcher.batch import run_gather
    return on_server(text, lambda jobs, port, a: run_gather(jobs, port))


def run_all(text):
    from async_batch_fetcher.batch import run_all
    return on_server(text, lambda jobs, port, a: run_all(jobs, port))


def run_with_progress(text):
    from async_batch_fetcher.batch import run_with_progress
    return on_server(text, lambda jobs, port, a: run_with_progress(jobs, port, sys.stdout))  # progress lines are printed


def run_stream(text):
    from async_batch_fetcher.batch import Fetcher

    async def work(jobs, port, a):
        return [r async for r in Fetcher(port, a.concurrency).stream(jobs)]

    return on_server(text, work)


def run_group(text):
    from async_batch_fetcher.batch import run_group
    return on_server(text, lambda jobs, port, a: run_group(jobs, port, concurrency=a.concurrency, timeout=a.timeout, strict=a.strict))


def run_cli(text):
    from async_batch_fetcher.cli import main
    return main(shlex.split(text))


HINT = "--jobs 5 --fail-every 3"
SERIAL = {"label": "run_serial", "hint": HINT, "run": run_serial}
GATHER = {"label": "run_gather", "hint": HINT, "run": run_gather}
ALL = {"label": "run_all", "hint": HINT, "run": run_all}
PROGRESS = {"label": "run_with_progress", "hint": HINT, "run": run_with_progress}
STREAM = {"label": "Fetcher.stream", "hint": "--jobs 6 --concurrency 2", "run": run_stream}
GROUP = {"label": "run_group", "hint": "--jobs 5 --timeout 0.5 --strict", "run": run_group}
CLI = {"label": "async-batch-fetcher", "hint": "--jobs 5 --fail-every 3", "run": run_cli}
HELP = ("cli", "--help", "more", "The command's options (it runs batches from Part 5)")
# starter code nothing can reach yet: run_serial and run_gather don't use it, and the command only through a stub
RESULTS_LATER = {"results": "starter code; run_all starts using it in Part 3"}

PARTS = {
    "1": {"entries": {"run_serial": SERIAL, "cli": CLI}, "not yet": RESULTS_LATER, "scenarios": [
        ("run_serial", "--jobs 3", "good", "Three jobs, one after another"),
        ("run_serial", "--jobs 4 --fail-every 2", "bad", "Job 2 fails, and the serial run stops there"),
        HELP,
    ]},
    "2": {"entries": {"run_gather": GATHER, "run_serial": SERIAL, "cli": CLI}, "not yet": RESULTS_LATER, "scenarios": [
        ("run_gather", "--jobs 5", "good", "Five jobs at once, with gather"),
        ("run_gather", "--jobs 4 --fail-every 2", "bad", "One failure sinks the whole gather"),
        HELP,
    ]},
    "3": {"entries": {"run_all": ALL, "run_with_progress": PROGRESS, "run_gather": GATHER, "cli": CLI}, "scenarios": [
        ("run_all", "--jobs 5", "good", "Five jobs at once, every one a result"),
        ("run_all", "--jobs 6 --fail-every 3", "bad", "Failures come back as results; the rest still finish"),
        ("run_with_progress", "--jobs 5 --fail-every 4", "more", "Progress printed as each job finishes"),
        HELP,
    ]},
    "4": {"entries": {"stream": STREAM, "run_all": ALL, "cli": CLI}, "scenarios": [
        ("stream", "--jobs 6 --concurrency 2", "good", "Results stream in, at most 2 in flight"),
        ("stream", "--jobs 6 --fail-every 3 --concurrency 2", "bad", "Failures stream in as results too"),
        HELP,
    ]},
    "5": {"entries": {"cli": CLI, "run_group": GROUP, "stream": STREAM}, "scenarios": [
        ("cli", "--jobs 5", "good", "The whole command: a batch and its report"),
        ("cli", "--jobs 6 --fail-every 3 --strict", "bad", "Strict: the first failure stops the batch"),
        ("run_group", "--jobs 4 --delay 0.2 --timeout 0.05", "more", "Each job's own deadline: they all time out"),
    ]},
}
