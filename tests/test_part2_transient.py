import httpx

from aiofetch.errors import PermanentError, TransientError
from aiofetch.retry import is_transient


def status_error(status, body=""):
    request = httpx.Request("GET", "http://api.test/items/1")
    response = httpx.Response(status, text=body, request=request)
    return httpx.HTTPStatusError(f"{status}", request=request, response=response)


def test_is_transient_retries_only_what_can_change():
    assert all(is_transient(status_error(s)) for s in (408, 409, 429, 500, 503))
    assert not any(is_transient(status_error(s)) for s in (400, 401, 403, 404, 422))
    assert not is_transient(status_error(429, '{"error": "insufficient_quota"}'))
    assert is_transient(httpx.ConnectError("refused"))
    assert is_transient(TransientError("/items/1", "503"))
    assert not is_transient(PermanentError("/items/1", "404"))
    assert not is_transient(ValueError("a bug"))
