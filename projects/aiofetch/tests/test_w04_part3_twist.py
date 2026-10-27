import asyncio

import pytest

from aiofetch.client import AiofetchClient
from aiofetch.errors import PermanentError
from aiofetch.flaky import FlakyAPI
from aiofetch.models import ITEM_RESPONSE, ItemFound, ItemMoved


def test_a_moved_answer_routes_to_its_own_shape():
    moved = {"status": "moved", "id": 3007, "movedTo": 7}
    answer = ITEM_RESPONSE.validate_python(moved)
    assert isinstance(answer, ItemMoved) and answer.moved_to == 7


def test_get_item_follows_one_move():
    api = FlakyAPI()

    async def main():
        async with AiofetchClient("http://api.test", transport=api) as client:
            return await client.get_item(3007)

    found = asyncio.run(main())
    assert isinstance(found, ItemFound) and found.item.id == 7
    assert api.calls["/v2/items/3007"] == 1 and api.calls["/v2/items/7"] == 1


def test_a_second_move_is_refused():
    async def main():
        async with AiofetchClient("http://api.test", transport=FlakyAPI()) as client:
            return await client.get_item(6007)

    with pytest.raises(PermanentError, match="moved twice"):
        asyncio.run(main())
