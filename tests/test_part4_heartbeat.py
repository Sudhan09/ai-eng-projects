from conftest import HEADERS
from fastapi.testclient import TestClient
from sse import frames

from stream_svc.deps import get_token_source
from stream_svc.fakes import FakeStreamingLLM
from stream_svc.main import create_app
from stream_svc.settings import get_settings


def test_an_idle_stream_sends_heartbeats(monkeypatch):
    monkeypatch.setenv("STREAM_HEARTBEAT_SECONDS", "0.05")
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_token_source] = lambda: FakeStreamingLLM(
        delay=0.3, jitter=0
    )
    with TestClient(app) as client:
        body = client.get(
            "/generate/stream",
            params={"prompt": "hi", "max_tokens": 2},
            headers=HEADERS,
        ).text
    assert body.count(": ping") >= 4
    assert [f["event"] for f in frames(body)] == ["token", "token", "done"]
