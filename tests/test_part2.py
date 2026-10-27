import asyncio
import time

from async_batch_fetcher.batch import run_gather, run_serial
from async_batch_fetcher.server import MockServer


def test_gather_keeps_input_order():
    async def main():
        server = MockServer(delay=0.01)
        port = await server.start()
        try:
            return await run_gather([5, 1, 3], port)
        finally:
            await server.stop()

    assert asyncio.run(main()) == ["payload-5", "payload-1", "payload-3"]


def test_gather_runs_the_jobs_at_the_same_time():
    async def main():
        server = MockServer(delay=0.05)
        port = await server.start()
        try:
            start = time.perf_counter()
            await run_serial(range(20), port)
            serial = time.perf_counter() - start
            start = time.perf_counter()
            await run_gather(range(20), port)
            return serial, time.perf_counter() - start, server.peak
        finally:
            await server.stop()

    serial, together, peak = asyncio.run(main())
    assert together < serial / 5
    assert peak == 20
