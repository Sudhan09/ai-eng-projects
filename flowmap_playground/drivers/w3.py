"""Week 3 (aiofetch): your paths through AiofetchClient.fetch_many, on ChaosAPI (W3 has no python -m aiofetch)."""

import asyncio

import httpx
from _input import scripted

from aiofetch.chaos import ChaosAPI
from aiofetch.client import AiofetchClient


def run_fetch_many(text):
    paths, script = scripted(text)

    async def go():
        async with AiofetchClient("http://api.test", transport=httpx.MockTransport(ChaosAPI(script=script))) as client:
            return await client.fetch_many(paths)

    return asyncio.run(go())


ENTRIES = {"fetch_many": {"label": "client.fetch_many", "hint": "/items/1 /items/3=404 /items/5=503,200", "run": run_fetch_many}}
