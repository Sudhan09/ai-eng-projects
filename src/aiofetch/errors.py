class FetchError(Exception):
    transient = False

    def __init__(self, url, reason):
        super().__init__(f"{url}: {reason}")
        self.url = url
        self.reason = reason


class TransientError(FetchError):
    transient = True

    def __init__(self, url, reason, retry_after=None):
        super().__init__(url, reason)
        if retry_after is not None and retry_after >= 0:
            self.retry_after = retry_after
        else:
            self.retry_after = None


class PermanentError(FetchError):
    transient = False
