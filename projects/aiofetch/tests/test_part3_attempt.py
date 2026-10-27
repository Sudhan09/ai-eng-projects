import asyncio

import pytest

from aiofetch.client import AiofetchClient
from aiofetch.errors import TransientError
from aiofetch.flaky import FlakyAPI


def one_attempt(chaos, path, timeout=10.0):
    """One timed attempt through the client's pooled transport, no retries."""

    async def main():
        transport = chaos
        async with AiofetchClient(
            "http://api.test", transport=transport, timeout=timeout
        ) as client:
            return await client._attempt(path, None), client.stats.attempts

    return asyncio.run(main())


def test_one_attempt_returns_the_payload_and_counts_itself():
    assert one_attempt(FlakyAPI(), "/items/7") == ({"id": "7", "name": "item 7"}, 1)


def test_a_hung_attempt_becomes_a_transient_timeout():
    with pytest.raises(TransientError, match="timeout"):
        one_attempt(FlakyAPI(script={"/items/7": ["hang"]}), "/items/7", timeout=0.05)
