import asyncio

import httpx

from aiofetch.chaos import ChaosAPI
from aiofetch.errors import FetchError, TransientError
from aiofetch.retry import retrying
from aiofetch.transport import get_json, make_client


def run_tenacity(answers, retry_after="1"):
    """Fetch /items/1 through the tenacity policy: (outcome, chaos, sleeps)."""
    chaos = ChaosAPI(script={"/items/1": answers}, retry_after=retry_after)
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    async def main():
        transport = httpx.MockTransport(chaos)
        async with make_client("http://api.test", transport=transport) as client:
            async for attempt in retrying(4, sleep=fake_sleep):
                with attempt:
                    return await get_json(client, "/items/1")

    try:
        outcome = asyncio.run(main())
    except FetchError as exc:
        outcome = exc
    return outcome, chaos, sleeps


def test_the_tenacity_policy_behaves_like_the_loop():
    outcome, chaos, sleeps = run_tenacity([503, 503, 200])
    assert outcome == {"id": "1", "name": "item 1"}
    assert chaos.calls["/items/1"] == 3 and len(sleeps) == 2
    outcome, chaos, _ = run_tenacity([503] * 5)
    assert isinstance(outcome, TransientError) and chaos.calls["/items/1"] == 4


def test_a_refused_connection_is_retried():
    outcome, chaos, _ = run_tenacity(["refused", 200])
    assert outcome == {"id": "1", "name": "item 1"} and chaos.calls["/items/1"] == 2
