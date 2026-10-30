from conftest import FakeSource
from fastapi.testclient import TestClient

from stream_svc.deps import get_token_source

BODY = {"prompt": "hello", "max_tokens": 5}


def test_no_key_means_no_source(app):
    built = []

    def counted_source():
        built.append(1)
        return FakeSource([" x"])

    app.dependency_overrides[get_token_source] = counted_source
    with TestClient(app) as client:
        assert client.post("/generate", json=BODY).status_code == 401
    assert built == []


def test_an_empty_key_is_refused(client):
    answer = client.post("/generate", json=BODY, headers={"X-API-Key": ""})
    assert answer.status_code == 401
