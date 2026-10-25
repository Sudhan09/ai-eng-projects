import asyncio

import httpx
import pytest

from aiofetch.chaos import ChaosAPI
from aiofetch.client import AiofetchClient


def client_for(chaos, **options):
    options.setdefault("backoff_base", 0.001)
    transport = httpx.MockTransport(chaos)
    return AiofetchClient("http://api.test", transport=transport, **options)


async def cancel_midway(client, delay):
    batch = asyncio.create_task(client.fetch_many([f"/items/{n}" for n in range(10)]))
    await asyncio.sleep(delay)
    batch.cancel()
    try:
        await batch
    except asyncio.CancelledError:
        pass  # the batch was cancelled, as asked


def test_one_failing_url_is_one_failed_result():
    chaos = ChaosAPI(script={"/items/3": [404]})

    async def main():
        async with client_for(chaos) as client:
            return await client.fetch_many([f"/items/{n}" for n in range(6)])

    results = asyncio.run(main())
    assert [r.url for r in results] == [f"/items/{n}" for n in range(6)]
    assert [r.url for r in results if not r.ok] == ["/items/3"]
    assert results[3].error.reason == "404 Not Found"


def test_a_cancelled_batch_gives_every_permit_back():
    chaos = ChaosAPI(latency=0.05)

    async def main():
        async with client_for(chaos, max_concurrency=5) as client:
            await cancel_midway(client, 0.01)
            return client.sem._value

    assert asyncio.run(main()) == 5
    assert chaos.peak == 5 and chaos.in_flight == 0


def test_100_cancel_cycles_leak_no_permit():
    async def main():
        leaked = 0
        async with client_for(ChaosAPI(latency=0.01), max_concurrency=5) as client:
            for cycle in range(100):
                await cancel_midway(client, cycle % 4 * 0.003)
                leaked += 5 - client.sem._value
        return leaked

    assert asyncio.run(main()) == 0


def test_results_keep_input_order_when_later_paths_answer_first():
    async def handler(request):
        n = int(request.url.path.split("/")[-1])
        await asyncio.sleep(0.03 - n * 0.01)  # /items/2 answers first, /items/0 last
        return httpx.Response(200, json={"n": n})

    async def main():
        transport = httpx.MockTransport(handler)
        async with AiofetchClient("http://api.test", transport=transport) as client:
            return await client.fetch_many(["/items/0", "/items/1", "/items/2"])

    results = asyncio.run(main())
    assert [r.value["n"] for r in results] == [0, 1, 2]


def test_a_bug_in_the_transport_crashes_the_batch():
    def handler(request):
        raise TypeError("a bug in the transport")

    async def main():
        transport = httpx.MockTransport(handler)
        async with AiofetchClient("http://api.test", transport=transport) as client:
            await client.fetch_many(["/items/1"])

    with pytest.raises(ExceptionGroup) as info:
        asyncio.run(main())
    assert isinstance(info.value.exceptions[0], TypeError)
