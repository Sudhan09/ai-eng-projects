"""Week 4 (aiofetch): python -m aiofetch with your paths, or client.get_item with your ids, on FlakyAPI (the fake).

For main, only the network under httpx is faked: your settings, make_client and HttpxTransport all run as they would.
"""

import asyncio
import os

import httpx
from _input import scripted

from aiofetch.__main__ import main
from aiofetch.client import AiofetchClient
from aiofetch.flaky import FlakyAPI
from aiofetch.settings import get_settings


def fake_network(api):
    """An httpx client made without a transport talks to the fake instead of the network."""
    real = httpx.AsyncClient.__init__

    def init(self, *args, transport=None, **kwargs):
        real(self, *args, transport=transport or httpx.MockTransport(api), **kwargs)

    httpx.AsyncClient.__init__ = init


def run_main(text):
    paths, script = scripted(text)
    for name in [n for n in os.environ if n.startswith("AIOFETCH_")]:
        del os.environ[name]  # only these settings, never your shell's
    os.environ.update(AIOFETCH_BASE_URL="http://api.test", AIOFETCH_API_KEY="playground-not-a-real-key")
    get_settings.cache_clear()
    fake_network(FlakyAPI(script=script))
    return asyncio.run(main(paths))


def run_get_item(text):
    ids, script = scripted(text, lambda i: f"/v2/items/{i}")
    if not all(i.isdigit() for i in ids):
        raise ValueError("get_item takes item ids, e.g. 7 1500 3007")  # before any of your code runs

    async def go():
        async with AiofetchClient("http://api.test", transport=FlakyAPI(script=script)) as client:
            return [await client.get_item(int(i)) for i in ids]

    return asyncio.run(go())


ENTRIES = {
    "main": {"label": "python -m aiofetch", "hint": "/v2/items/7   /items/1=503,503,200", "run": run_main},
    "get_item": {"label": "client.get_item", "hint": "7   1500   3007", "run": run_get_item},
}
