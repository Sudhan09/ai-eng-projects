import asyncio

import pytest
from aiofetch import AiofetchClient
from aiofetch.errors import CircuitOpenError, PermanentError, TransientError
from aiofetch.fake import FakeTransport
from aiofetch.flaky import FlakyAPI
from conftest import HEADERS
from fastapi.testclient import TestClient

from stream_svc.errors import UpstreamFailed, from_fetch_error
from stream_svc.main import create_app
from stream_svc.sources import UpstreamSource

URL = "/v1/tokens"
BODY = {"prompt": "hello", "max_tokens": 5}


def test_each_fetch_error_becomes_the_status_a_caller_can_act_on():
    cases = [
        (TransientError(URL, "timeout (ReadTimeout)"), 504, None),
        (TransientError(URL, "429 Too Many Requests", retry_after=7.0), 503, 7),
        (TransientError(URL, "503 Service Unavailable"), 503, 5),
        (CircuitOpenError(URL, "circuit OPEN"), 503, 5),
        (PermanentError(URL, "404 Not Found"), 502, None),
    ]
    for exc, status, retry_after in cases:
        mapped = from_fetch_error(exc, 5)
        assert (mapped.status, mapped.retry_after) == (status, retry_after), exc


def test_a_page_that_isnt_a_token_page_is_upstream_failed():
    bad = FakeTransport({URL: {"tokens": [7], "done": False}})  # a number, not a string

    async def main():
        async with AiofetchClient(
            "http://provider.test", attempts=1, transport=bad
        ) as client:
            return [token async for token in UpstreamSource(client).stream("hi", 5)]

    with pytest.raises(UpstreamFailed):
        asyncio.run(main())


def test_a_busy_provider_passes_its_retry_after_on():
    busy = FlakyAPI(script={URL: [429]}, retry_after="7")
    with TestClient(create_app(transport=busy)) as client:
        answer = client.post("/generate", json=BODY, headers=HEADERS)
    assert answer.headers["retry-after"] == "7"
