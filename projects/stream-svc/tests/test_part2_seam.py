import asyncio

from conftest import FakeSource


async def collect(source, prompt, max_tokens):
    return [token async for token in source.stream(prompt, max_tokens)]


def test_a_fake_source_fits_the_seam_and_stops_at_max_tokens():
    source = FakeSource([" a", " b", " c"])
    assert asyncio.run(collect(source, "hello", 2)) == [" a", " b"]
    assert asyncio.run(collect(source, "hello", 10)) == [" a", " b", " c"]
