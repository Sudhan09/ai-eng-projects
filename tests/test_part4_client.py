import asyncio

import httpx
from test_part4_bucket import FakeClock  # Step 4.1's fake clock

from aiofetch.chaos import ChaosAPI
from aiofetch.client import AiofetchClient
from aiofetch.limiter import max_in_window


def two_requests(**options):
    """/items/6, then /items/7, through a client on the fake clock: its sleeps."""
    clock = FakeClock()

    async def main():
        async with AiofetchClient(
            "http://api.test",
            transport=httpx.MockTransport(ChaosAPI()),
            clock=clock,
            sleep=clock.sleep,
            **options,
        ) as client:
            await client.get_json("/items/6")
            await client.get_json("/items/7")

    asyncio.run(main())
    return clock.sleeps


def test_the_client_waits_on_its_limiter_not_on_429s():
    # one wait of 60/59 seconds: the second request waited for its token
    assert two_requests(requests_per_minute=60) == [1.0169491525423728]


def test_without_a_limit_the_client_never_waits():
    assert two_requests() == []


def test_200_requests_never_put_more_than_60_in_a_minute():
    clock = FakeClock()
    seen = []

    def handler(request):
        seen.append(clock())  # when the fake server saw this request
        return httpx.Response(200, json={"ok": True})

    async def main():
        async with AiofetchClient(
            "http://api.test",
            transport=httpx.MockTransport(handler),
            requests_per_minute=60,
            clock=clock,
            sleep=clock.sleep,
        ) as client:
            await client.fetch_many([f"/items/{n}" for n in range(200)])

    asyncio.run(main())
    assert len(seen) == 200
    assert max_in_window(seen) <= 60
