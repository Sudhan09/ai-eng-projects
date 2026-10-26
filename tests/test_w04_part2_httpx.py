import asyncio

import httpx
import pytest

from aiofetch.errors import PermanentError, TransientError
from aiofetch.flaky import FlakyAPI
from aiofetch.transport import HttpxTransport, get_json


def over_httpx(api):
    """An HttpxTransport whose httpx client answers from `api`, with no network."""
    client = httpx.AsyncClient(base_url="http://api.test", transport=httpx.MockTransport(api))
    return HttpxTransport(client)


def test_the_httpx_transport_hands_back_every_status():
    async def main():
        transport = over_httpx(FlakyAPI(script={"/items/7": [404]}))
        response = await transport.get("/items/7")
        await transport.aclose()
        return response

    response = asyncio.run(main())
    assert response.status == 404 and response.json() == {"error": "no such item"}


def test_a_timeout_becomes_a_transient_error():
    async def main():
        transport = over_httpx(FlakyAPI(script={"/items/7": ["timeout"]}))
        await transport.get("/items/7")

    with pytest.raises(TransientError, match="ReadTimeout"):
        asyncio.run(main())


def test_get_json_decodes_a_200_and_raises_for_a_404():
    async def main():
        transport = over_httpx(FlakyAPI(script={"/items/8": [404]}))
        value = await get_json(transport, "/items/7")
        with pytest.raises(PermanentError, match="404 Not Found"):
            await get_json(transport, "/items/8")
        return value

    assert asyncio.run(main()) == {"id": "7", "name": "item 7"}


# my own: a refused connection is a transient error too
def test_a_refused_connection_becomes_a_transient_error():
    async def main():
        transport = over_httpx(FlakyAPI(script={"/items/7": ["refused"]}))
        await transport.get("/items/7")

    with pytest.raises(TransientError) as caught:
        asyncio.run(main())
    assert str(caught.value) == "/items/7: ConnectError"
