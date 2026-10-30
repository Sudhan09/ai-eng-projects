"""Shared test setup: the key every client sends, and an app per test."""

import pytest
from fastapi.testclient import TestClient

from stream_svc.main import create_app

HEADERS = {"X-API-Key": "test-key-0000"}  # every client sends its key; Part 5 checks it


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client