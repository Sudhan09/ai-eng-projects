import asyncio
import random
import time


class TokenBucket:
    def __init__(self, capacity, rate, *, clock=time.monotonic, sleep=asyncio.sleep):
        self.capacity = capacity
        self.rate = rate
        self.clock = clock
        self.sleep = sleep
        self.tokens = capacity
        self.updated = clock()

    @classmethod
    def for_limit(cls, limit, per=60.0, *, burst=1.0, **kwargs):
        rate = (limit - burst) / per
        return cls(burst, rate, **kwargs)

    def refill(self):
        now = self.clock()
        elapsed = now - self.updated
        if elapsed < 0:
            elapsed = 0
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.updated = now

    def wait_time(self, n=1.0):
        if n > self.capacity:
            raise ValueError(f"{n} tokens can never fit in a bucket of {self.capacity}")
        self.refill()
        missing = n - self.tokens
        if missing <= 0:
            return 0.0
        return missing / self.rate

    def take(self, n=1.0):
        self.tokens -= n


class DualLimiter:
    def __init__(
        self,
        rpm,
        tpm,
        *,
        max_request_tokens=None,
        clock=time.monotonic,
        sleep=asyncio.sleep,
        jitter=0.0,
        rng=None,
    ):
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

    async def acquire(self, tokens=1.0):
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


def max_in_window(times, window=60.0):
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
