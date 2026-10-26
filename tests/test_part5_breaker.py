import asyncio

import pytest
from test_part4_bucket import FakeClock  # Step 4.1's fake clock

from aiofetch.breaker import CircuitBreaker
from aiofetch.errors import CircuitOpenError, PermanentError, TransientError


def open_breaker(clock):
    breaker = CircuitBreaker(failure_threshold=5, reset_timeout=30, clock=clock)

    async def failing():
        raise TransientError("/items/1", "503")

    async def main():
        for _ in range(5):
            with pytest.raises(TransientError):
                await breaker.call(failing)

    asyncio.run(main())
    return breaker


def test_the_breaker_opens_after_five_failures_then_fails_fast():
    breaker = open_breaker(FakeClock())
    calls = 0

    async def counted():
        nonlocal calls
        calls += 1

    async def main():
        for _ in range(20):
            with pytest.raises(CircuitOpenError):
                await breaker.call(counted)

    asyncio.run(main())
    assert breaker.state == "OPEN"
    assert calls == 0 and breaker.short_circuits == 20


def test_after_the_reset_timeout_one_probe_decides():
    async def ok():
        return "up"

    async def still_down():
        raise TransientError("/items/1", "503")

    clock = FakeClock()
    healed = open_breaker(clock)
    clock.now += 30
    assert asyncio.run(healed.call(ok)) == "up"
    assert healed.state == "CLOSED"
    broken = open_breaker(clock)
    clock.now += 30
    with pytest.raises(TransientError):
        asyncio.run(broken.call(still_down))
    assert broken.state == "OPEN" and broken.opened_at == clock.now


def test_a_404_never_trips_the_breaker():
    breaker = CircuitBreaker(failure_threshold=5)

    async def missing():
        raise PermanentError("/items/1", "404")

    async def main():
        for _ in range(10):
            with pytest.raises(PermanentError):
                await breaker.call(missing)

    asyncio.run(main())
    assert breaker.state == "CLOSED"


def test_a_second_call_during_the_probe_is_refused():
    clock = FakeClock()
    breaker = open_breaker(clock)
    clock.now += 30

    async def slow_probe():
        await asyncio.sleep(0.05)
        return "up"

    async def instant():
        return "never runs"

    async def main():
        probe = asyncio.create_task(breaker.call(slow_probe, "/items/7"))
        await asyncio.sleep(0)  # let the probe start
        with pytest.raises(CircuitOpenError, match="/items/7: circuit HALF_OPEN"):
            await breaker.call(instant, "/items/7")
        return await probe

    assert asyncio.run(main()) == "up"


def test_a_cancelled_probe_leaves_the_breaker_open():
    clock = FakeClock()
    breaker = open_breaker(clock)
    clock.now += 30

    async def hang():
        await asyncio.sleep(3600)

    async def main():
        probe = asyncio.create_task(breaker.call(hang, "/items/7"))
        await asyncio.sleep(0)
        assert breaker.state == "HALF_OPEN"
        probe.cancel()
        with pytest.raises(asyncio.CancelledError):
            await probe

    asyncio.run(main())
    assert breaker.state == "OPEN"
