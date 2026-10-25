import httpx

from aiofetch.transport import error_for, retry_after


def test_retry_after_reads_seconds_and_fails_closed():
    headers = ["10", "0", None, "soon", "-5"]
    assert [retry_after(h) for h in headers] == [10.0, 0.0, None, None, None]


def test_error_for_puts_the_hint_on_the_error():
    request = httpx.Request("GET", "http://api.test/items/7")
    busy = httpx.Response(429, headers={"Retry-After": "10"}, request=request)
    assert error_for("/items/7", busy).retry_after == 10.0
    vague = httpx.Response(429, headers={"Retry-After": "soon"}, request=request)
    assert error_for("/items/7", vague).retry_after is None
