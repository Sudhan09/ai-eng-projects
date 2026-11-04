from conftest import HEADERS
from fastapi.testclient import TestClient
from sse import frames

from stream_svc.fakes import FakeProvider
from stream_svc.main import create_app

HELLO = {"prompt": "hello", "max_tokens": 5}


def test_hello_runs_through_every_part():
    provider = FakeProvider()
    app = create_app(transport=provider)
    with TestClient(app, headers={"Origin": "http://web.test"}) as client:
        generated = client.post("/generate", json=HELLO, headers=HEADERS)
        stream = client.get("/generate/stream", params=HELLO, headers=HEADERS)
        refused = client.get(
            "/generate/stream", params=HELLO, headers={"X-API-Key": "nope"}
        )
        upstream = client.get("/health").json()["upstream"]
    assert generated.json() == {
        "text": "soon one by waiting of",
        "tokens": 5,
    }  # Parts 1 and 2
    got = frames(stream.text)  # Part 3
    assert "".join(f["data"] for f in got[:-1]) == " soon one by waiting of"
    assert got[-1] == {"event": "done", "data": "[DONE]"}
    record = app.state.telemetry[-1]  # Part 4
    assert (record.outcome, record.tokens) == ("done", 5)
    assert record.request_id == stream.headers["x-request-id"]
    assert stream.headers["access-control-allow-origin"] == "http://web.test"
    assert refused.json()["error"]["code"] == "unauthorized"  # Part 5
    assert upstream == {"breaker_state": "CLOSED", "attempts": 2, "retries": 0}
    assert provider.calls == 2  # one page each for /generate and the stream
