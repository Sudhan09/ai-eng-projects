import asyncio

from aiofetch.client import AiofetchClient
from aiofetch.fake import FakeTransport


def test_the_client_runs_on_a_fake_with_no_network():
    fake = FakeTransport({"/items/7": {"id": "7"}})

    async def main():
        async with AiofetchClient("http://nowhere.invalid", transport=fake) as client:
            return await client.get_json("/items/7", {"fields": "id"})

    assert asyncio.run(main()) == {"id": "7"}
    assert fake.requests == [("/items/7", {"fields": "id"})]
    assert fake.closed
