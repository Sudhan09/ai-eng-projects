import asyncio
import time
from dataclasses import dataclass

from .errors import FetchError, TransientError
from .limiter import DualLimiter
from .results import Result
from .retry import retrying
from .transport import get_json, make_client


@dataclass
class Stats:
    attempts: int = 0
    retries: int = 0


class AiofetchClient:
    def __init__(
        self,
        base_url,
        *,
        max_concurrency=20,
        attempts=4,
        requests_per_minute=None,
        tokens_per_minute=None,
        timeout=10.0,
        backoff_base=0.5,
        backoff_cap=30.0,
        transport=None,
        clock=time.monotonic,
        sleep=asyncio.sleep,
        logger=None,
    ):
        self.base_url = base_url
        self.max_concurrency = max_concurrency
        self.attempts = attempts
        self.timeout = timeout
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.transport = transport
        self.sleep = sleep
        self.logger = logger
        self.stats = Stats()
        self.http = None
        if requests_per_minute is None:
            self.limiter = None
        else:
            if tokens_per_minute is None:
                tokens_per_minute = requests_per_minute
            self.limiter = DualLimiter(
                requests_per_minute, tokens_per_minute, clock=clock, sleep=sleep
            )
        self.sem = asyncio.BoundedSemaphore(max_concurrency)

    async def __aenter__(self):
        self.http = make_client(
            self.base_url,
            max_connections=self.max_concurrency,
            timeout=self.timeout,
            transport=self.transport,
        )
        return self

    async def __aexit__(self, *exc):
        await self.http.aclose()

    async def _attempt(self, path, params):
        self.stats.attempts += 1
        try:
            async with asyncio.timeout(self.timeout):
                return await get_json(self.http, path, params)
        except TimeoutError:
            raise TransientError(path, "timeout") from None

    async def get_json(self, path, params=None, *, tokens=1):
        async with self.sem:
            if self.limiter is not None:
                await self.limiter.acquire(tokens)
            return await self._with_retries(path, params)

    async def _with_retries(self, path, params):
        policy = retrying(
            self.attempts,
            base=self.backoff_base,
            cap=self.backoff_cap,
            sleep=self.sleep,
            logger=self.logger,
            on_retry=self._count_retry,
        )
        async for attempt in policy:
            with attempt:
                return await self._attempt(path, params)

    def _count_retry(self, state):
        self.stats.retries += 1

    async def fetch_many(self, paths):
        tasks = []
        async with asyncio.TaskGroup() as tg:
            for path in paths:
                tasks.append(tg.create_task(self._one(path)))
        results = []
        for task in tasks:
            results.append(task.result())
        return results

    async def _one(self, path):
        start = time.perf_counter()
        try:
            value = await self.get_json(path)
        except FetchError as exc:
            return Result(path, error=exc, seconds=time.perf_counter() - start)
        return Result(path, value=value, seconds=time.perf_counter() - start)
