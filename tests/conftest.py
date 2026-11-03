"""Shared test setup: the test environment, a FakeSource, and an app whose lifespan runs."""

import hashlib

import pytest
from fastapi.testclient import TestClient

from stream_svc.main import create_app
from stream_svc.settings import get_settings

KEY = "test-key-0000"  # an obvious stand-in: the tests' only key
HEADERS = {"X-API-Key": KEY}
ENV = {
    "STREAM_API_KEY_SHA256": hashlib.sha256(KEY.encode()).hexdigest(),
    "STREAM_FAKE_UPSTREAM": "true",
    "STREAM_UPSTREAM_ATTEMPTS": "1",
    "STREAM_UPSTREAM_TIMEOUT": "0.2",
    "STREAM_CORS_ORIGINS": '["http://web.test"]',
}


class FakeSource:
    """A TokenSource that streams the tokens it was given, at once."""

    def __init__(self, tokens):
        self.tokens = tokens

    async def stream(self, prompt, max_tokens):
        for token in self.tokens[:max_tokens]:
            yield token


@pytest.fixture(autouse=True)
def stream_env(monkeypatch):
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()  # the next get_settings() reads this environment
    yield
    get_settings.cache_clear()


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    with TestClient(
        app
    ) as client:  # `with` runs the lifespan: startup now, shutdown after
        yield client
