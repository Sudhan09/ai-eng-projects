from test_w04_part2_fakes import checkers  # Step 2.4's helper: (mypy, pyright)

SEEDED = """\
from aiofetch.client import AiofetchClient


def report(client: AiofetchClient) -> None:
    client.stats.breaker_state = "BROKEN"
"""


def test_both_checkers_refuse_a_state_that_isnt_one_of_the_three(tmp_path):
    mypy, pyright = checkers(tmp_path, SEEDED)
    assert mypy.count(": error:") == 1 and "BROKEN" in mypy, mypy
    assert "1 error, 0 warnings" in pyright and "BROKEN" in pyright, pyright
