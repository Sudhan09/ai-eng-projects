import time

import pytest

from aiofetch.limiter import TokenBucket


class FakeClock:
    """Time that moves only when the test says so, so waiting costs nothing."""

    def __init__(self, start=1000.0):
        self.now = start
        self.sleeps = []

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def test_the_bucket_refills_at_its_rate():
    clock = FakeClock()
    bucket = TokenBucket(2, 1.0, clock=clock)
    assert bucket.wait_time(2) == 0
    bucket.take(2)
    assert bucket.wait_time(1) == 1.0
    clock.now += 0.5
    assert bucket.wait_time(1) == 0.5


def test_the_bucket_runs_on_the_monotonic_clock_and_survives_a_step_back():
    assert TokenBucket(1, 1.0).clock is time.monotonic
    clock = FakeClock()
    bucket = TokenBucket(1, 1.0, clock=clock)
    bucket.take(1)
    clock.now -= 3600  # a wall clock stepped back an hour
    assert bucket.wait_time(1) == 1.0  # not 3,601 seconds


def test_a_request_bigger_than_the_bucket_fails_at_once():
    with pytest.raises(ValueError, match="6 tokens can never fit in a bucket of 5"):
        TokenBucket(5, 1.0).wait_time(6)


def test_an_idle_bucket_still_holds_only_its_capacity():
    clock = FakeClock()
    bucket = TokenBucket(2, 1.0, clock=clock)
    clock.now += 3600  # an hour idle
    assert bucket.wait_time(2) == 0.0
    bucket.take(2)
    assert bucket.wait_time(1) == 1.0
