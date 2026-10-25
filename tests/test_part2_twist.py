from test_part2_loop import run_loop  # Step 2.3's helper: (outcome, chaos, sleeps)
from test_part2_tenacity import run_tenacity  # Step 2.4's helper, the same shape


def test_a_valid_retry_after_is_honoured():
    for run in (run_loop, run_tenacity):
        _, _, sleeps = run([429, 200], retry_after="10")
        assert sleeps == [10.0]


def test_an_unreadable_retry_after_falls_back_to_the_backoff():
    for header in ("soon", "-5", "Wed, 21 Oct 2026 07:28:00 GMT"):
        for run in (run_loop, run_tenacity):
            _, _, [slept] = run([429, 200], retry_after=header)
            assert 0 <= slept <= 0.5  # the first backoff, not the unreadable hint
