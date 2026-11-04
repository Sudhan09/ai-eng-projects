from conftest import HEADERS, FakeSource
from fastapi.testclient import TestClient

from stream_svc import settings as settings_module
from stream_svc.deps import get_token_source
from stream_svc.main import create_app
from stream_svc.settings import Settings, get_settings

BODY = {"prompt": "hello", "max_tokens": 5}


def test_settings_are_built_once_across_20_requests(monkeypatch):
    built = []

    class CountedSettings(Settings):
        def __init__(self):
            built.append(1)
            super().__init__()

    monkeypatch.setattr(settings_module, "Settings", CountedSettings)
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        for _ in range(20):
            assert (
                client.post("/generate", json=BODY, headers=HEADERS).status_code == 200
            )
    assert len(built) == 1


def test_each_request_resolves_get_settings_once_however_many_need_it(app):
    calls = []

    def counted():
        calls.append(1)
        return get_settings()

    app.dependency_overrides[get_settings] = counted
    with TestClient(app) as client:
        for _ in range(20):
            client.post("/generate", json=BODY, headers=HEADERS)
    assert len(calls) == 20


def test_an_override_swaps_in_a_fake_token_source(app):
    app.dependency_overrides[get_token_source] = lambda: FakeSource(
        [" fake", " tokens"]
    )
    with TestClient(app) as client:
        answer = client.post("/generate", json=BODY, headers=HEADERS)
    assert answer.json() == {"text": "fake tokens", "tokens": 2}
