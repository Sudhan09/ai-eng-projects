import time

from .errors import CircuitOpenError, FetchError


class CircuitBreaker:
    def __init__(self, failure_threshold=5, reset_timeout=30.0, *, clock=time.monotonic):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.clock = clock
        self.state = "CLOSED"
        self.failures = 0
        self.opened_at = 0.0
        self.short_circuits = 0

    async def call(self, fn, url=""):
        if self.state == "OPEN" and self.clock() - self.opened_at >= self.reset_timeout:
            self.state = "HALF_OPEN"
        elif self.state != "CLOSED":
            self.short_circuits += 1
            raise CircuitOpenError(url, f"circuit {self.state}")

        try:
            result = await fn()
        except FetchError as exc:
            if exc.transient:
                self._failed()
            else:
                self._succeeded()
            raise
        except BaseException:
            if self.state == "HALF_OPEN":
                self._open()
            raise
        self._succeeded()
        return result

    def _failed(self):
        self.failures += 1
        if self.state == "HALF_OPEN" or self.failures >= self.failure_threshold:
            self._open()

    def _succeeded(self):
        self.state = "CLOSED"
        self.failures = 0

    def _open(self):
        self.state = "OPEN"
        self.opened_at = self.clock()
