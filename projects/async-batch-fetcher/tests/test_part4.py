import asyncio

import pytest

from async_batch_fetcher.batch import Fetcher
from async_batch_fetcher.server import MockServer


def test_never_more_than_the_limit_in_flight():
    async def main():
        server = MockServer(delay=0.02)
        port = await server.start()
        try:
            fetcher = Fetcher(port, concurrency=5)
            results = await asyncio.gather(*(fetcher.fetch(i) for i in range(50)))
            return results, fetcher.peak, server.peak
        finally:
            await server.stop()

    results, peak, server_peak = asyncio.run(main())
    assert all(r.ok for r in results)
    assert peak == 5 and server_peak <= 5


def test_stream_yields_every_job_once():
    async def main():
        server = MockServer(delay=0.01)
        port = await server.start()
        try:
            async with Fetcher(port, concurrency=4) as fetcher:
                return sorted([r.job_id async for r in fetcher.stream(range(30))])
        finally:
            await server.stop()

    assert asyncio.run(main()) == list(range(30))


def test_stopping_the_stream_early_leaves_no_task_behind():
    async def main():
        server = MockServer(delay=0.01)
        port = await server.start()
        try:
            async with Fetcher(port, concurrency=3) as fetcher:
                async for _result in fetcher.stream(range(30)):
                    break
        finally:
            await server.stop()
        others = asyncio.all_tasks() - {asyncio.current_task()}
        return [t.done() for t in fetcher.tasks], others

    done, others = asyncio.run(main())
    assert all(done) and others == set()


def test_a_bounded_semaphore_refuses_an_extra_release():
    async def main():
        sem = asyncio.BoundedSemaphore(1)
        with pytest.raises(ValueError):
            sem.release()

    asyncio.run(main())
