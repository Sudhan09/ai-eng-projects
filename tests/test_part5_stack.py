import asyncio

import httpx
import pytest

from aiofetch.chaos import ChaosAPI
from aiofetch.client import AiofetchClient
from aiofetch.errors import FetchError, TransientError


def client_for(chaos, **options):
    options.setdefault("backoff_base", 0.001)
    options.setdefault("requests_per_minute", 60_000)
    transport = httpx.MockTransport(chaos)
    return AiofetchClient("http://api.test", transport=transport, **options)


def test_stats_count_attempts_retries_and_the_breaker_state():
    async def main():
        async with client_for(ChaosAPI(script={"/items/1": [503, 503, 200]})) as client:
            await client.get_json("/items/1")
            return client.stats

    stats = asyncio.run(main())
    assert (stats.attempts, stats.retries, stats.breaker_state) == (3, 2, "CLOSED")


def test_a_retried_blip_is_one_breaker_failure_not_four():
    async def main():
        async with client_for(ChaosAPI(script={"/items/1": [503] * 4})) as client:
            with pytest.raises(TransientError):
                await client.get_json("/items/1")
            return client.breaker.failures, client.stats.attempts

    assert asyncio.run(main()) == (1, 4)


def test_an_outage_opens_the_breaker_and_then_spends_no_network():
    chaos = ChaosAPI()
    chaos.down = True

    async def main():
        kinds = []
        async with client_for(chaos, attempts=2) as client:
            for n in range(8):
                try:
                    await client.get_json(f"/items/{n}")
                except FetchError as exc:
                    kinds.append(type(exc).__name__)
            return kinds, client.stats.breaker_state

    kinds, state = asyncio.run(main())
    assert state == "OPEN"
    assert kinds.count("TransientError") == 5 and kinds.count("CircuitOpenError") == 3
    assert chaos.total == 10  # 5 calls x 2 attempts; the 3 refused calls cost nothing
