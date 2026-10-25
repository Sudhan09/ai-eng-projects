import asyncio

import httpx
import pytest

from aiofetch.chaos import ChaosAPI
from aiofetch.client import AiofetchClient
from aiofetch.errors import TransientError


def test_a_hung_attempt_times_out_and_the_retry_succeeds():
    chaos = ChaosAPI(script={"/items/1": ["hang"]})

    async def main():
        transport = httpx.MockTransport(chaos)
        async with AiofetchClient(
            "http://api.test", transport=transport, timeout=0.05, backoff_base=0.001
        ) as client:
            value = await client.get_json("/items/1")
            return value, client.stats.attempts, client.stats.retries, client.sem._value

    assert asyncio.run(main()) == ({"id": "1", "name": "item 1"}, 2, 1, 20)


def test_a_call_that_never_succeeds_still_gives_its_permit_back():
    chaos = ChaosAPI(script={"/items/7": [503] * 4})

    async def main():
        transport = httpx.MockTransport(chaos)
        async with AiofetchClient(
            "http://api.test", transport=transport, backoff_base=0.001
        ) as client:
            with pytest.raises(TransientError):
                await client.get_json("/items/7")
            return client.stats.attempts, client.stats.retries, client.sem._value

    assert asyncio.run(main()) == (4, 3, 20)
