import asyncio
import time

from conftest import HEADERS

from stream_svc.deps import get_token_source
from stream_svc.fakes import FakeStreamingLLM
from stream_svc.lab import read_then_leave
from stream_svc.serving import running


def test_read_then_leave_hangs_up_after_its_tokens(app):
    app.dependency_overrides[get_token_source] = lambda: FakeStreamingLLM()
    with running(app) as url:
        before = time.perf_counter()
        left = asyncio.run(read_then_leave(url, "hello", 50, 5, headers=HEADERS))
        after = time.perf_counter()
    assert before < left < after  # the moment it hung up, by the same clock
