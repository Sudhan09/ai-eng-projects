from aiofetch.errors import FetchError, PermanentError, TransientError


def test_failures_say_whether_a_retry_could_help():  # Week 2's flag test, unchanged
    assert TransientError.transient and not PermanentError.transient
    assert issubclass(TransientError, FetchError) and issubclass(PermanentError, FetchError)


def test_an_error_keeps_its_url_and_reason():
    error = TransientError("/items/7", "503 Service Unavailable")
    assert error.url == "/items/7" and error.reason == "503 Service Unavailable"
    assert error.retry_after is None  # no wait hint until Part 2's twist sets one
    assert str(error) == "/items/7: 503 Service Unavailable"
