"""The ways to run a batch: serial, gather, failures-as-results, bounded, grouped."""

import asyncio
import hashlib
import sys
from collections.abc import AsyncIterator, Iterable
from typing import TextIO

from async_batch_fetcher.client import fetch
from async_batch_fetcher.errors import FetchError, PermanentError, TransientError
from async_batch_fetcher.results import Result, status


# ---- Part 1 ---------------------------------------------------------------
async def run_serial(job_ids: Iterable[int], port: int) -> list[str]:
    payloads = []
    for job_id in job_ids:
        payload = await fetch(job_id, port)
        payloads.append(payload)
    return payloads


# ---- Part 2 ---------------------------------------------------------------
async def run_gather(job_ids: Iterable[int], port: int) -> list[str]:
    coros = [fetch(job_id, port) for job_id in job_ids]
    payloads = await asyncio.gather(*coros)
    return payloads


# ---- Part 3 ---------------------------------------------------------------
async def fetch_result(job_id: int, port: int) -> Result:
    try:
        value = await fetch(job_id, port)
        return Result(job_id=job_id, value=value)
    except FetchError as e:
        return Result(job_id=job_id, error=e)


async def run_all(job_ids: list[int], port: int) -> list[Result]:
    coros = [fetch_result(job_id, port) for job_id in job_ids]
    results = await asyncio.gather(*coros)
    return results


async def run_with_progress(
    job_ids: list[int], port: int, out: TextIO = sys.stderr
) -> list[Result]:
    finished = {}
    failures = 0
    coros = [fetch_result(job_id, port) for job_id in job_ids]
    for n, next_done in enumerate(asyncio.as_completed(coros), 1):
        result = await next_done
        finished[result.job_id] = result
        if not result.ok:
            failures += 1
        print(
            f"done {n}/{len(job_ids)} job {result.job_id} {status(result)}"
            f" ({failures} failed so far)",
            file=out,
        )
    return [finished[job_id] for job_id in job_ids]


# ---- Part 4 ---------------------------------------------------------------
class Fetcher:
    """At most `concurrency` fetches in flight, counted as they run."""

    def __init__(self, port: int, concurrency: int = 20) -> None:  # GIVEN
        self.port = port
        self.sem = asyncio.BoundedSemaphore(concurrency)
        self.in_flight = 0
        self.peak = 0
        self.tasks: set[asyncio.Task[Result]] = set()

    async def fetch(self, job_id: int, timeout: float | None = None) -> Result:
        # TODO (you write this) - plan in plain English first
        raise NotImplementedError

    async def stream(self, job_ids: Iterable[int]) -> AsyncIterator[Result]:
        # TODO (you write this) - plan in plain English first
        raise NotImplementedError

    async def __aenter__(self) -> "Fetcher":  # GIVEN
        return self

    async def __aexit__(self, *exc: object) -> None:
        # cancel whatever is still running, then wait until every task is gone
        # TODO (you write this) - plan in plain English first
        raise NotImplementedError


# ---- Part 5 ---------------------------------------------------------------
def checksum(payload: str, rounds: int = 2_000) -> str:  # GIVEN
    """A slow, blocking step: hash the payload over and over."""
    digest = payload.encode()
    for _ in range(rounds):
        digest = hashlib.sha256(digest).digest()
    return digest.hex()[:12]


async def guarded(
    fetcher: Fetcher, job_id: int, timeout: float, strict: bool, sums: dict[int, str]
) -> Result:
    # TODO (you write this) - plan in plain English first
    raise NotImplementedError


async def run_group(
    job_ids: list[int],
    port: int,
    concurrency: int = 20,
    timeout: float = 1.0,
    strict: bool = False,
) -> tuple[list[Result], dict[int, str], int]:
    # TODO (you write this) - plan in plain English first
    raise NotImplementedError
