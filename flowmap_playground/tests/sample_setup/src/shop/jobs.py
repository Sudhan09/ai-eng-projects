"""Jobs that run on their own."""

from contextlib import contextmanager


def nightly() -> int:
    """Needs nothing: a start the playground can run to reach report."""
    return report(rows=["a", "b", "c"])


def report(rows: list[str], limit: int = 1000) -> int:
    """Only nightly calls it, and no test does."""
    return len(rows[:limit])


@contextmanager
def opened(name: str):
    yield f"handle:{name}"


def use(handle: str) -> str:
    return handle.upper()


def needs_db(conn: "Connection") -> int:  # noqa: F821  (a type from outside: nothing of yours makes it)
    return 1


def weekly(run: bool = False) -> int:
    """Calls audit only when told to: run as it is, it never gets there."""
    if run:
        return audit(["x"])
    return 0


def audit(entries) -> int:
    """No test reaches it; weekly calls it, but not with what it needs nothing."""
    return len(entries)


def weigh(item: str, scale: int) -> int:
    """One test calls it in a thread, one calls it directly."""
    return len(item) * scale


def tally(rows: list[int], scale: int) -> int:
    """One test gives it 3,000 rows (too long to step through), another gives it 2."""
    return sum(double(r) for r in rows) * scale


def double(x: int) -> int:
    return 2 * x
