import asyncio
import random
import time
from collections.abc import Awaitable, Callable, Iterable

Clock = Callable[[], float]  # a function that returns the time now, in seconds
Sleep = Callable[[float], Awaitable[None]]  # a function you await to wait some seconds


class TokenBucket:
    def __init__(
        self,
        capacity: float,
        rate: float,
        *,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.capacity = capacity
        self.rate = rate
        self.clock = clock
        self.sleep = sleep
        self.tokens = capacity
        self.updated = clock()

    @classmethod
    def for_limit(
        cls,
        limit: float,
        per: float = 60.0,
        *,
        burst: float = 1.0,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> "TokenBucket":
        rate = (limit - burst) / per
        return cls(burst, rate, clock=clock, sleep=sleep)

    def refill(self) -> None:
        now = self.clock()
        elapsed = now - self.updated
        if elapsed < 0:
            elapsed = 0
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.updated = now

    def wait_time(self, n: float = 1.0) -> float:
        if n > self.capacity:
            raise ValueError(f"{n} tokens can never fit in a bucket of {self.capacity}")
        self.refill()
        missing = n - self.tokens
        if missing <= 0:
            return 0.0
        return missing / self.rate

    def take(self, n: float = 1.0) -> None:
        self.tokens -= n


class DualLimiter:
    def __init__(
        self,
        rpm: float,
        tpm: float,
        *,
        max_request_tokens: float | None = None,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
        jitter: float = 0.0,
        rng: random.Random | None = None,
    ) -> None:
        if max_request_tokens is None:
            max_request_tokens = tpm / rpm
        if rng is None:
            rng = random.Random()
        self.requests = TokenBucket.for_limit(rpm, burst=1, clock=clock)
        self.tokens = TokenBucket.for_limit(tpm, burst=max_request_tokens, clock=clock)
        self.sleep = sleep
        self.jitter = jitter
        self.rng = rng
        self.lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        async with self.lock:
            while True:
                wait_requests = self.requests.wait_time(1)
                wait_tokens = self.tokens.wait_time(tokens)
                wait = max(wait_requests, wait_tokens)
                if wait <= 1e-9:
                    break
                await self.sleep(wait + self.rng.uniform(0, self.jitter))
            self.requests.take(1)
            self.tokens.take(tokens)


def max_in_window(times: Iterable[float], window: float = 60.0) -> int:
    ordered = sorted(times)
    most = 0
    for end in ordered:
        count = 0
        for t in ordered:
            if end - window - 1e-9 <= t <= end:
                count += 1
        if count > most:
            most = count
    return most
