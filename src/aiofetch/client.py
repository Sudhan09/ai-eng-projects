import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Concatenate, Protocol, Self

from tenacity import RetryCallState

from .breaker import CircuitBreaker, State
from .errors import FetchError, TransientError
from .limiter import Clock, DualLimiter, Sleep
from .results import Result
from .retry import retrying
from .transport import HttpTransport, HttpxTransport, get_json, make_client


@dataclass
class Stats:
    attempts: int = 0
    retries: int = 0
    breaker_state: State = "CLOSED"
    seconds: list[float] = field(default_factory=list)


class HasStats(Protocol):
    stats: Stats


def timed[S: HasStats, **P, R](
    fn: Callable[Concatenate[S, P], Awaitable[R]],
) -> Callable[Concatenate[S, P], Awaitable[R]]:
    async def wrapper(self: S, /, *args: P.args, **kwargs: P.kwargs) -> R:
        start = time.perf_counter()
        try:
            return await fn(self, *args, **kwargs)
        finally:
            self.stats.seconds.append(time.perf_counter() - start)

    return wrapper


class AiofetchClient:
    def __init__(
        self,
        base_url: str,
        *,
        max_concurrency: int = 20,
        attempts: int = 4,
        requests_per_minute: float | None = None,
        tokens_per_minute: float | None = None,
        failure_threshold: int = 5,
        reset_timeout: float = 30.0,
        timeout: float = 10.0,
        backoff_base: float = 0.5,
        backoff_cap: float = 30.0,
        transport: HttpTransport | None = None,
        headers: Mapping[str, str] | None = None,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
        logger: logging.Logger | None = None,
    ) -> None:
        self.base_url = base_url
        self.max_concurrency = max_concurrency
        self.attempts = attempts
        self.timeout = timeout
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.transport = transport
        self.headers = headers
        self.sleep = sleep
        self.logger = logger
        self.stats = Stats()
        if requests_per_minute is None:
            self.limiter: DualLimiter | None = None
        else:
            if tokens_per_minute is None:
                tokens_per_minute = requests_per_minute
            self.limiter = DualLimiter(
                requests_per_minute, tokens_per_minute, clock=clock, sleep=sleep
            )
        self.breaker = CircuitBreaker(failure_threshold, reset_timeout, clock=clock)
        self.sem = asyncio.BoundedSemaphore(max_concurrency)

    def _transport(self) -> HttpTransport:
        if self.transport is None:
            raise RuntimeError("use AiofetchClient inside 'async with'")
        return self.transport

    async def __aenter__(self) -> Self:
        if self.transport is None:
            client = make_client(
                self.base_url,
                max_connections=self.max_concurrency,
                timeout=self.timeout,
                headers=self.headers,
            )
            self.transport = HttpxTransport(client)
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._transport().aclose()

    async def _attempt(self, path: str, params: Mapping[str, str] | None) -> object:
        self.stats.attempts += 1
        try:
            async with asyncio.timeout(self.timeout):
                return await get_json(self._transport(), path, params)
        except TimeoutError:
            raise TransientError(path, "timeout") from None

    @timed
    async def get_json(
        self, path: str, params: Mapping[str, str] | None = None, *, tokens: float = 1
    ) -> object:
        async with self.sem:
            if self.limiter is not None:
                await self.limiter.acquire(tokens)

            async def retried_call() -> object:
                return await self._with_retries(path, params)

            try:
                return await self.breaker.call(retried_call, path)
            finally:
                self.stats.breaker_state = self.breaker.state

    async def _with_retries(self, path: str, params: Mapping[str, str] | None) -> object:
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
        raise RuntimeError("the retry policy always returns or raises before this")

    def _count_retry(self, state: RetryCallState) -> None:
        self.stats.retries += 1

    async def fetch_many(self, paths: Iterable[str]) -> list[Result[object]]:
        tasks: list[asyncio.Task[Result[object]]] = []
        async with asyncio.TaskGroup() as tg:
            for path in paths:
                tasks.append(tg.create_task(self._one(path)))
        results: list[Result[object]] = []
        for task in tasks:
            results.append(task.result())
        return results

    async def _one(self, path: str) -> Result[object]:
        start = time.perf_counter()
        try:
            value = await self.get_json(path)
        except FetchError as exc:
            return Result(path, error=exc, seconds=time.perf_counter() - start)
        return Result(path, value=value, seconds=time.perf_counter() - start)
