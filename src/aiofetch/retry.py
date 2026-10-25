import asyncio
import logging
import random

import httpx
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from .errors import FetchError
from .transport import is_transient_status


def is_transient(exc):
    if isinstance(exc, FetchError):
        return exc.transient
    if isinstance(exc, httpx.HTTPStatusError):
        return is_transient_status(exc.response.status_code, exc.response.text)
    if isinstance(exc, httpx.TransportError):
        return True
    return False


def full_jitter(attempt, *, base, cap, rng):
    ceiling = min(cap, base * 2**attempt)
    return rng.uniform(0, ceiling)


async def retry_call(fn, *, attempts=4, base=0.5, cap=30.0, sleep=asyncio.sleep, rng=None):
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
            if exc.retry_after is not None:
                await sleep(exc.retry_after)
            else:
                await sleep(full_jitter(attempt, base=base, cap=cap, rng=rng))


def wait_with_retry_after(fallback):
    def wait(state):
        exc = state.outcome.exception()
        hint = getattr(exc, "retry_after", None)
        if hint is not None:
            return hint
        return fallback(state)

    return wait


def retrying(attempts=4, *, base=0.5, cap=30.0, sleep=asyncio.sleep, logger=None, on_retry=None):

    if logger is None:
        logger = logging.getLogger("aiofetch")
    log_warning = before_sleep_log(logger, logging.WARNING)

    def before_sleep(state):
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
