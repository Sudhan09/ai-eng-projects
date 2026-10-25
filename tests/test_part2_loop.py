import asyncio
import random

import httpx
import pytest

from aiofetch.chaos import ChaosAPI
from aiofetch.errors import FetchError, PermanentError, TransientError
from aiofetch.retry import retry_call
from aiofetch.transport import get_json, make_client


def run_loop(answers, retry_after="1"):
    """Fetch /items/1 through retry_call: (outcome, chaos, sleeps)."""
    chaos = ChaosAPI(script={"/items/1": answers}, retry_after=retry_after)
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    async def main():
        transport = httpx.MockTransport(chaos)
        async with make_client("http://api.test", transport=transport) as client:

            async def call():
                return await get_json(client, "/items/1")

            return await retry_call(call, sleep=fake_sleep, rng=random.Random(1))

    try:
        outcome = asyncio.run(main())
    except FetchError as exc:  # the last failure, after the retries
        outcome = exc
    return outcome, chaos, sleeps


def test_the_loop_needs_exactly_three_attempts_for_503_503_200():
    outcome, chaos, sleeps = run_loop([503, 503, 200])
    assert outcome == {"id": "1", "name": "item 1"}
    assert chaos.calls["/items/1"] == 3
    assert len(sleeps) == 2
    assert 0 <= sleeps[0] <= 0.5 and 0 <= sleeps[1] <= 1.0  # full jitter, base 0.5


def test_a_401_is_tried_once():
    outcome, chaos, sleeps = run_loop([401])
    assert isinstance(outcome, PermanentError)
    assert chaos.calls["/items/1"] == 1 and sleeps == []


def test_the_loop_gives_up_after_four_attempts():
    outcome, chaos, _ = run_loop([503] * 5)
    assert isinstance(outcome, TransientError)
    assert chaos.calls["/items/1"] == 4


def test_zero_attempts_is_refused():
    async def call():
        return "never called"

    with pytest.raises(ValueError, match="attempts must be at least 1"):
        asyncio.run(retry_call(call, attempts=0))
