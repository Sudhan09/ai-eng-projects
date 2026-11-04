import json

from conftest import HEADERS
from fastapi.testclient import TestClient
from sse import frames

from stream_svc.fakes import FakeProvider
from stream_svc.main import create_app


def test_a_failure_after_the_first_page_becomes_an_error_frame_then_done():
    app = create_app(transport=FakeProvider(fail_from=2, status=503))
    with TestClient(app) as client:
        answer = client.get(
            "/generate/stream",
            params={"prompt": "hello", "max_tokens": 20},
            headers=HEADERS,
        )
    got = frames(answer.text)
    assert answer.status_code == 200  # sent before the failure, so it can't change
    assert [f["event"] for f in got] == ["token"] * 8 + ["error", "done"]
    error = json.loads(got[8]["data"])["error"]
    assert error["code"] == "upstream_busy"
    assert error["request_id"] == answer.headers["x-request-id"]
    assert got[-1]["data"] == "[DONE]"
