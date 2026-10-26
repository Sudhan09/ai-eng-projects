import time
from collections.abc import Awaitable, Callable

from .errors import CircuitOpenError, FetchError
from .limiter import Clock


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 30.0,
        *,
        clock: Clock = time.monotonic,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.clock = clock
        self.state = "CLOSED"
        self.failures = 0
        self.opened_at = 0.0
        self.short_circuits = 0

    async def call[T](self, fn: Callable[[], Awaitable[T]], url: str = "") -> T:
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

    def _failed(self) -> None:
        self.failures += 1
        if self.state == "HALF_OPEN" or self.failures >= self.failure_threshold:
            self._open()

    def _succeeded(self) -> None:
        self.state = "CLOSED"
        self.failures = 0

    def _open(self) -> None:
        self.state = "OPEN"
        self.opened_at = self.clock()
