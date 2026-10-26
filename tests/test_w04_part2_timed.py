import asyncio

import pytest
from test_w04_part2_fakes import checkers  # Step 2.4's helper: (mypy, pyright)

from aiofetch.client import AiofetchClient
from aiofetch.errors import PermanentError
from aiofetch.flaky import FlakyAPI

SEEDED = """\
from aiofetch.client import AiofetchClient


async def main(client: AiofetchClient) -> None:
    await client.get_json(7)
"""


def test_timed_records_each_call_and_keeps_its_result():
    async def main():
        client = AiofetchClient("http://api.test", transport=FlakyAPI())
        async with client:
            value = await client.get_json("/items/1")
            await client.get_json("/items/2")
        return value, client.stats.seconds

    value, seconds = asyncio.run(main())
    assert value == {"id": "1", "name": "item 1"}
    assert len(seconds) == 2 and all(s >= 0 for s in seconds)


def test_both_checkers_catch_one_wrong_argument_through_the_decorator(tmp_path):
    mypy, pyright = checkers(tmp_path, SEEDED)
    assert mypy.count(": error:") == 1 and '"get_json"' in mypy, mypy
    assert "1 error, 0 warnings" in pyright and 'parameter "path"' in pyright, pyright


# my own: a call that raises still adds its time
def test_a_failed_call_is_timed_too():
    async def main():
        flaky = FlakyAPI(script={"/items/2": [404]})
        async with AiofetchClient("http://api.test", transport=flaky) as client:
            with pytest.raises(PermanentError):
                await client.get_json("/items/2")
            return client.stats.seconds

    assert len(asyncio.run(main())) == 1
