import asyncio

from aiofetch import AiofetchClient
from aiofetch.fake import FakeTransport

from stream_svc.fakes import FakeProvider, token_at
from stream_svc.sources import UpstreamSource


async def collect(transport, prompt, max_tokens, **kwargs):
    async with AiofetchClient(
        "http://provider.test", attempts=1, transport=transport
    ) as client:
        source = UpstreamSource(client, **kwargs)
        return [token async for token in source.stream(prompt, max_tokens)]


def test_the_source_reads_pages_until_it_has_max_tokens():
    provider = FakeProvider()
    tokens = asyncio.run(collect(provider, "hello", 5, page_size=2))
    assert tokens == [token_at("hello", i) for i in range(5)]
    assert provider.calls == 3  # pages of 2, 2 and 1


def test_the_source_stops_at_a_done_page_and_at_an_empty_one():
    done = FakeTransport({"/v1/tokens": {"tokens": [" a", " b"], "done": True}})
    assert asyncio.run(collect(done, "x", 10)) == [" a", " b"]
    empty = FakeTransport({"/v1/tokens": {"tokens": [], "done": False}})
    assert asyncio.run(collect(empty, "x", 10)) == []
    assert (len(done.requests), len(empty.requests)) == (1, 1)


def test_twenty_tokens_come_from_three_pages_of_eight():
    provider = FakeProvider()
    tokens = asyncio.run(collect(provider, "hello", 20))
    assert tokens == [token_at("hello", i) for i in range(20)]
    assert provider.calls == 3  # pages of 8, 8 and 4
