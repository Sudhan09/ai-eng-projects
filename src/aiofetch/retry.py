import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

import httpx
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from .errors import FetchError, TransientError
from .limiter import Sleep
from .transport import is_transient_status


def is_transient(exc: BaseException) -> bool:
    if isinstance(exc, FetchError):
        return exc.transient
    if isinstance(exc, httpx.HTTPStatusError):
        return is_transient_status(exc.response.status_code, exc.response.text)
    if isinstance(exc, httpx.TransportError):
        return True
    return False


def full_jitter(attempt: int, *, base: float, cap: float, rng: random.Random) -> float:
    ceiling = min(cap, base * 2**attempt)
    return rng.uniform(0, ceiling)


async def retry_call[T](
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 4,
    base: float = 0.5,
    cap: float = 30.0,
    sleep: Sleep = asyncio.sleep,
    rng: random.Random | None = None,
) -> T:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if rng is None:
        rng = random.Random()
    for attempt in range(attempts):
        try:
            return await fn()
        except FetchError as exc:
            if attempt == attempts - 1:
                last = True
            else:
                last = False
            if not is_transient(exc) or last:
                raise
            if isinstance(exc, TransientError) and exc.retry_after is not None:
                await sleep(exc.retry_after)
            else:
                await sleep(full_jitter(attempt, base=base, cap=cap, rng=rng))
    raise RuntimeError("retry_call: the loop always returns or raises before this")


def wait_with_retry_after(
    fallback: Callable[[RetryCallState], float],
) -> Callable[[RetryCallState], float]:
    def wait(state: RetryCallState) -> float:
        if state.outcome is None:
            return fallback(state)
        exc = state.outcome.exception()
        if isinstance(exc, TransientError) and exc.retry_after is not None:
            return exc.retry_after
        return fallback(state)

    return wait


def retrying(
    attempts: int = 4,
    *,
    base: float = 0.5,
    cap: float = 30.0,
    sleep: Sleep = asyncio.sleep,
    logger: logging.Logger | None = None,
    on_retry: Callable[[RetryCallState], None] | None = None,
) -> AsyncRetrying:
    if logger is None:
        logger = logging.getLogger("aiofetch")
    log_warning = before_sleep_log(logger, logging.WARNING)

    def before_sleep(state: RetryCallState) -> None:
        if on_retry is not None:
            on_retry(state)
        log_warning(state)

    return AsyncRetrying(
        stop=stop_after_attempt(attempts),
        wait=wait_with_retry_after(wait_random_exponential(multiplier=base, max=cap)),
        retry=retry_if_exception(is_transient),
        reraise=True,
        sleep=sleep,
        before_sleep=before_sleep,
    )
