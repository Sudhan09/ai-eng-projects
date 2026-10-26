import asyncio

import httpx
import pytest

from aiofetch.errors import FetchError, PermanentError, TransientError
from aiofetch.flaky import FlakyAPI
from aiofetch.transport import HttpxTransport, get_json, make_client


def fetch(chaos, path):
    async def main():
        transport = httpx.MockTransport(chaos)
        async with make_client("http://api.test", transport=transport) as client:
            return await get_json(HttpxTransport(client), path)

    return asyncio.run(main())


def test_get_json_returns_the_decoded_payload():
    assert fetch(FlakyAPI(), "/items/7") == {"id": "7", "name": "item 7"}


def test_statuses_become_typed_errors():
    chaos = FlakyAPI(script={"/items/1": [503], "/items/2": [404], "/items/3": [429]})
    kinds = []
    for path in ("/items/1", "/items/2", "/items/3"):
        with pytest.raises(FetchError) as info:
            fetch(chaos, path)
        kinds.append(type(info.value).__name__)
    assert kinds == ["TransientError", "PermanentError", "TransientError"]


def test_an_exhausted_quota_is_permanent():
    with pytest.raises(PermanentError):
        fetch(FlakyAPI(script={"/items/1": ["quota"]}), "/items/1")


def test_a_timeout_is_transient():
    with pytest.raises(TransientError, match="ReadTimeout"):
        fetch(FlakyAPI(script={"/items/1": ["timeout"]}), "/items/1")


def test_a_refused_connection_is_transient():
    with pytest.raises(TransientError) as info:
        fetch(FlakyAPI(script={"/items/7": ["refused"]}), "/items/7")
    assert str(info.value) == "/items/7: ConnectError"
