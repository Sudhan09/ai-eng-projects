class FetchError(Exception):
    transient: bool = False

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{url}: {reason}")
        self.url = url
        self.reason = reason


class TransientError(FetchError):
    transient = True

    def __init__(self, url: str, reason: str, retry_after: float | None = None) -> None:
        super().__init__(url, reason)
        self.retry_after: float | None = None
        if retry_after is not None and retry_after >= 0:
            self.retry_after = retry_after


class PermanentError(FetchError):
    transient = False


class CircuitOpenError(FetchError):
    transient = False
