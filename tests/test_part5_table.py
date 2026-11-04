import pytest
from aiofetch.flaky import FlakyAPI
from conftest import HEADERS
from fastapi.testclient import TestClient

from stream_svc.main import create_app

BODY = {"prompt": "hello", "max_tokens": 5}
JSON = {**HEADERS, "Content-Type": "application/json"}
NOT_INT = "Input should be a valid integer, unable to parse string as an integer"
MESSAGES = {
    "validation_error": "The request doesn't match the API.",
    "malformed_json": "The request body isn't valid JSON.",
    "unauthorized": "A valid API key is required.",
    "upstream_busy": "The model provider is busy. Try again later.",
    "upstream_timeout": "The model provider didn't answer in time.",
}


def problem(field, text):
    return [{"field": f"body.{field}", "problem": text}]


# name, what is sent, the provider (Week 4's FlakyAPI), status, code, details
CASES = [
    ("missing field", {"json": {"max_tokens": 5}, "headers": HEADERS}, None,
     422, "validation_error", problem("prompt", "Field required")),
    ("oversized prompt", {"json": {"prompt": "x" * 4001}, "headers": HEADERS}, None,
     422, "validation_error", problem("prompt", "String should have at most 4000 characters")),
    ("non-int max_tokens", {"json": {"prompt": "hi", "max_tokens": "ten"}, "headers": HEADERS},
     None, 422, "validation_error", problem("max_tokens", NOT_INT)),
    ("absent key", {"json": BODY}, None,
     401, "unauthorized", []),
    ("wrong key", {"json": BODY, "headers": {"X-API-Key": "test-key-0001"}}, None,
     401, "unauthorized", []),
    ("upstream 429", {"json": BODY, "headers": HEADERS}, {"/v1/tokens": [429]},
     503, "upstream_busy", []),
    ("upstream timeout", {"json": BODY, "headers": HEADERS}, {"/v1/tokens": ["hang"]},
     504, "upstream_timeout", []),
    ("malformed JSON", {"content": b'{"prompt": "hi"', "headers": JSON}, None,
     400, "malformed_json", []),
]  # fmt: skip


@pytest.mark.parametrize("name, sent, script, status, code, details", CASES)
def test_each_bad_request_gets_its_status_and_the_exact_envelope(
    name, sent, script, status, code, details
):
    provider = FlakyAPI(script=script, retry_after="7") if script else None
    with TestClient(create_app(transport=provider)) as client:
        answer = client.post("/generate", **sent)
    assert answer.status_code == status, name
    request_id = answer.headers["x-request-id"]
    error = {
        "code": code,
        "message": MESSAGES[code],
        "request_id": request_id,
        "details": details,
    }
    assert answer.json() == {"error": error}, name
