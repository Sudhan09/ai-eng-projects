import asyncio
import time

from stream_svc.fakes import FakeStreamingLLM, token_at


def test_the_streaming_fake_yields_the_fake_models_tokens_one_pause_each():
    async def main():
        start = time.perf_counter()
        fake = FakeStreamingLLM(delay=0.01, jitter=0)
        tokens = [token async for token in fake.stream("hello", 3)]
        return tokens, time.perf_counter() - start

    tokens, seconds = asyncio.run(main())
    assert tokens == [token_at("hello", i) for i in range(3)]
    assert seconds >= 0.03  # three pauses of 0.01 s
