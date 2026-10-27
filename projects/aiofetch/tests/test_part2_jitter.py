import random

from aiofetch.retry import full_jitter


def jitter(attempt, rng):
    return full_jitter(attempt, base=0.5, cap=30.0, rng=rng)


def test_full_jitter_draws_up_to_the_backoff():
    waits = [jitter(attempt, random.Random(7)) for attempt in (0, 1, 10)]
    assert waits == [0.16191638241658118, 0.32383276483316237, 9.71498294499487]
    rng = random.Random(1)
    assert all(0 <= jitter(10, rng) <= 30.0 for _ in range(1000))
