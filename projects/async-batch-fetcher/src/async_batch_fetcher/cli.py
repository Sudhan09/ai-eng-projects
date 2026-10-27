"""The async-batch-fetcher command: run a batch against a local MockServer."""

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime

from async_batch_fetcher.batch import run_group
from async_batch_fetcher.results import failure_kinds, log_line, partition
from async_batch_fetcher.server import MockServer


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="async-batch-fetcher", description=__doc__)
    p.add_argument("--jobs", type=int, default=200, help="how many jobs (default 200)")
    p.add_argument("--concurrency", type=int, default=20, help="max in flight")
    p.add_argument("--delay", type=float, default=0.05, help="server delay, seconds")
    p.add_argument("--fail-every", type=int, default=0, help="every Nth job fails")
    p.add_argument("--timeout", type=float, default=1.0, help="per-job deadline, s")
    p.add_argument("--strict", action="store_true", help="first 404 stops the batch")
    p.add_argument("--log", help="write one logparse line per job to this file")
    p.add_argument("--timing", action="store_true", help="print the run time to stderr")
    return p


async def run(args: argparse.Namespace) -> dict:
    async with MockServer(delay=args.delay, fail_every=args.fail_every) as server:
        start = datetime.now(UTC)
        results, sums, peak = await run_group(
            list(range(args.jobs)),
            server.port,
            concurrency=args.concurrency,
            timeout=args.timeout,
            strict=args.strict,
        )
    if args.log:
        with open(args.log, "w", encoding="utf-8") as fh:
            fh.writelines(log_line(r, start) + "\n" for r in results)
    ok, _failed = partition(results)
    orphaned = len(asyncio.all_tasks() - {asyncio.current_task()})
    return {
        "jobs": len(results),
        "ok": len(ok),
        "failed": failure_kinds(results),
        "checksums": len(sums),
        "peak_in_flight": peak,
        "orphaned_tasks": orphaned,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    began = time.perf_counter()
    aborted = None
    try:
        try:
            report = asyncio.run(run(args))
        except* Exception as group:  # noqa: BLE001 - a strict abort arrives as an ExceptionGroup
            aborted = group.exceptions[0]  # (return isn't allowed inside except*)
    except KeyboardInterrupt:  # asyncio.run cancelled every task first
        print("cancelled: every task stopped", file=sys.stderr)
        return 130
    if aborted is not None:
        print(f"aborted: {aborted}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    if args.timing:
        print(f"took {time.perf_counter() - began:.2f} s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
