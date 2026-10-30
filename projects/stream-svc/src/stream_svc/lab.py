import asyncio
import time

import httpx2
from aiofetch.results import percentile
from fastapi import FastAPI

from stream_svc.serving import running


def lab_app(delay=0.05):
    lab = FastAPI()

    @lab.get("/slow_async")
    async def slow_async():
        await asyncio.sleep(delay)
        return {"slept": delay}

    @lab.get("/slow_sync")
    def slow_sync():
        time.sleep(delay)
        return {"slept": delay}

    @lab.get("/slow_blocking")
    async def slow_blocking():
        time.sleep(delay)  # wrong on purpose: blocks the whole loop  # noqa: ASYNC251
        return {"slept": delay}

    return lab


async def load(url, path, requests=200, concurrency=50):
    gate = asyncio.Semaphore(concurrency)
    limits = httpx2.Limits(max_connections=concurrency)
    async with httpx2.AsyncClient(base_url=url, timeout=60, limits=limits) as client:

        async def one():
            async with gate:
                start = time.perf_counter()
                response = await client.get(path)
                response.raise_for_status()
                return time.perf_counter() - start

        return await asyncio.gather(*(one() for _ in range(requests)))


def main():
    start = time.perf_counter()
    total = 0
    with running(lab_app()) as url:
        print(f"cold start {time.perf_counter() - start:.2f} s")
        for path in ("/slow_async", "/slow_blocking"):
            wall = time.perf_counter()
            cpu = time.process_time()
            seconds = asyncio.run(load(url, path))
            wall = time.perf_counter() - wall
            cpu = time.process_time() - cpu
            total += len(seconds)
            p95 = percentile(seconds, 95)
            print(
                f"{path:<14} {len(seconds)} done  p95 {p95:.2f} s  {len(seconds) / wall:.0f} req/s  CPU {cpu / wall * 100:.0f}%"
            )
    print("total completed", total)


if __name__ == "__main__":
    main()
