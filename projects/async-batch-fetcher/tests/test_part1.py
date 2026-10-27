import asyncio
import time

import pytest

from async_batch_fetcher.batch import run_serial
from async_batch_fetcher.client import fetch
from async_batch_fetcher.errors import FetchError, PermanentError, TransientError
from async_batch_fetcher.server import MockServer


def test_fetch_returns_the_payload():
    async def main():
        server = MockServer(delay=0.01)
        port = await server.start()
        try:
            return await fetch(7, port)
        finally:
            await server.stop()

    assert asyncio.run(main()) == "payload-7"


def test_failing_jobs_raise_typed_errors():
    async def main():
        server = MockServer(delay=0.01, fail_every=10)
        port = await server.start()
        try:
            with pytest.raises(TransientError):
                await fetch(9, port)
            with pytest.raises(PermanentError):
                await fetch(19, port)
        finally:
            await server.stop()

    asyncio.run(main())


def test_failures_say_whether_a_retry_could_help():
    assert TransientError.transient and not PermanentError.transient
    assert issubclass(TransientError, FetchError) and issubclass(
        PermanentError, FetchError
    )


def test_serial_waits_once_per_job():
    async def main():
        server = MockServer(delay=0.05)
        port = await server.start()
        try:
            start = time.perf_counter()
            values = await run_serial(range(10), port)
            return values, time.perf_counter() - start, server.peak
        finally:
            await server.stop()

    values, seconds, peak = asyncio.run(main())
    assert values == [f"payload-{i}" for i in range(10)]
    assert seconds >= 0.5
    assert peak == 1
