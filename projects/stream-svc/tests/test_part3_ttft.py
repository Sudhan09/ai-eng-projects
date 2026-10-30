import asyncio

from conftest import HEADERS

from stream_svc.deps import get_token_source
from stream_svc.fakes import FakeStreamingLLM
from stream_svc.lab import time_stream
from stream_svc.serving import running


def test_the_first_token_arrives_within_150_ms(app):
    app.dependency_overrides[get_token_source] = lambda: FakeStreamingLLM()
    with running(app) as url:
        first, gaps = asyncio.run(time_stream(url, "hello", 200, headers=HEADERS))
    assert first < 0.150
    assert len(gaps) == 199
