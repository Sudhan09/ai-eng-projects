import asyncio
import random

import pytest
from test_part4_bucket import FakeClock  # Step 4.1's fake clock

from aiofetch.limiter import DualLimiter, max_in_window


def test_no_minute_ever_holds_more_than_the_rpm():
    clock = FakeClock()
    limiter = DualLimiter(rpm=60, tpm=90_000, clock=clock, sleep=clock.sleep)
    admitted = []

    async def one_request():
        await limiter.acquire(tokens=1_000)
        admitted.append(clock())

    async def main():
        async with asyncio.TaskGroup() as tg:
            for _ in range(200):
                tg.create_task(one_request())

    asyncio.run(main())
    assert max_in_window(admitted) == 60
    per_minute = (len(admitted) - 1) / (admitted[-1] - admitted[0]) * 60
    assert 58 < per_minute <= 60


def test_the_token_budget_binds_for_big_requests():
    clock = FakeClock()
    limiter = DualLimiter(
        rpm=60, tpm=60_000, max_request_tokens=5_000, clock=clock, sleep=clock.sleep
    )
    admitted = []

    async def main():
        for _ in range(40):
            await limiter.acquire(tokens=5_000)
            admitted.append(clock())

    asyncio.run(main())
    assert max_in_window(admitted) == 12  # 12 x 5,000 tokens = 60,000 a minute


def test_a_request_bigger_than_the_token_bucket_fails_at_once():
    limiter = DualLimiter(rpm=60, tpm=60_000, max_request_tokens=5_000)
    with pytest.raises(ValueError):
        asyncio.run(limiter.acquire(tokens=6_000))


def test_jitter_wakes_waiters_apart():
    clock = FakeClock()
    limiter = DualLimiter(
        rpm=60, tpm=60, clock=clock, sleep=clock.sleep, jitter=0.5, rng=random.Random(7)
    )

    async def main():
        for _ in range(5):
            await limiter.acquire()

    asyncio.run(main())
    assert len(clock.sleeps) == 4 and len(set(clock.sleeps)) == 4  # no two waits alike
