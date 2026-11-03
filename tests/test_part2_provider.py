import asyncio

from stream_svc.fakes import FakeProvider, token_at

PAGE = {"prompt": "hello", "start": "0", "count": "3"}


def test_the_fake_provider_answers_pages_then_fails_on_cue():
    provider = FakeProvider(fail_from=2)

    async def main():
        first = await provider.get("/v1/tokens", PAGE)
        second = await provider.get("/v1/tokens", PAGE)
        await provider.aclose()
        return first, second

    first, second = asyncio.run(main())
    assert first.json() == {
        "tokens": [token_at("hello", i) for i in range(3)],
        "done": False,
    }
    assert second.status == 503
    assert (provider.calls, provider.closed) == (2, True)
