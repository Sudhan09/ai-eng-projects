import asyncio

import httpx

from aiofetch.flaky import FlakyAPI


def answers(chaos, paths):
    """Each path's (status, JSON body), through a plain httpx client on the fake."""

    async def main():
        transport = httpx.MockTransport(chaos)
        seen = []
        async with httpx.AsyncClient(base_url="http://api.test", transport=transport) as client:
            for path in paths:
                response = await client.get(path)
                seen.append((response.status_code, response.json()))
        return seen

    return asyncio.run(main())


def test_the_fake_follows_its_script_then_answers_200():
    chaos = FlakyAPI(script={"/items/7": [503]})
    assert answers(chaos, ["/items/7", "/items/7"]) == [
        (503, {"error": "busy"}),
        (200, {"id": "7", "name": "item 7"}),
    ]
    assert chaos.calls["/items/7"] == 2 and chaos.total == 2


def test_an_outage_answers_503_everywhere():
    chaos = FlakyAPI()
    chaos.down = True
    statuses = [status for status, _ in answers(chaos, ["/items/1", "/items/2"])]
    assert statuses == [503, 503]


def test_two_requests_at_once_peak_at_2_and_leave_none_in_flight():
    chaos = FlakyAPI(latency=0.01)

    async def main():
        transport = httpx.MockTransport(chaos)
        async with httpx.AsyncClient(base_url="http://api.test", transport=transport) as client:
            await asyncio.gather(client.get("/items/1"), client.get("/items/2"))

    asyncio.run(main())
    assert chaos.peak == 2 and chaos.in_flight == 0
