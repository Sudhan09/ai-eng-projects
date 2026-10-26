import asyncio

from aiofetch.client import AiofetchClient
from aiofetch.flaky import FlakyAPI
from aiofetch.models import ApiError, Item, ItemFound, ItemMissing


def test_get_item_returns_the_shape_the_server_sent():
    async def main():
        async with AiofetchClient("http://api.test", transport=FlakyAPI()) as client:
            return [await client.get_item(n) for n in (7, 1500, 2500)]

    found, missing, error = asyncio.run(main())
    assert found == ItemFound(status="ok", item=Item(id=7, name="item 7", priceCents=257))
    assert missing == ItemMissing(status="not_found", id=1500)
    assert error == ApiError(status="error", code="bad_id", message="no id 2500")
