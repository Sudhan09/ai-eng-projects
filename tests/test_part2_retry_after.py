from aiofetch.transport import Response, error_for, retry_after


def test_retry_after_reads_seconds_and_fails_closed():
    headers = ["10", "0", None, "soon", "-5"]
    assert [retry_after(h) for h in headers] == [10.0, 0.0, None, None, None]


def test_error_for_puts_the_hint_on_the_error():
    busy = Response(429, headers={"retry-after": "10"})
    assert error_for("/items/7", busy).retry_after == 10.0
    vague = Response(429, headers={"retry-after": "soon"})
    assert error_for("/items/7", vague).retry_after is None
