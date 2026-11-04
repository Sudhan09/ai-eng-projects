from aiofetch import AiofetchClient, HttpxTransport
from conftest import HEADERS
from fastapi.testclient import TestClient

from stream_svc import main
from stream_svc.fakes import FakeProvider
from stream_svc.main import create_app
from stream_svc.settings import get_settings

BODY = {"prompt": "hello", "max_tokens": 16}


def test_one_upstream_client_serves_every_request_and_closes_at_shutdown(monkeypatch):
    built = []

    class CountedClient(AiofetchClient):
        def __init__(self, *args, **kwargs):
            built.append(1)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(main, "AiofetchClient", CountedClient)
    provider = FakeProvider()
    with TestClient(create_app(transport=provider)) as client:
        for _ in range(20):
            client.post("/generate", json=BODY, headers=HEADERS)
        assert not provider.closed
    assert len(built) == 1
    assert provider.closed


def test_without_the_fake_the_client_uses_the_real_transport(monkeypatch):
    monkeypatch.setenv("STREAM_FAKE_UPSTREAM", "false")
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app):  # startup builds the client; no request is sent
        assert isinstance(app.state.upstream.transport, HttpxTransport)
