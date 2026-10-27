"""One Result per job, and the helpers that read a list of them."""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from async_batch_fetcher.errors import FetchError


@dataclass(frozen=True, slots=True)
class Result:
    job_id: int
    value: str | None = None
    error: FetchError | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def partition(results: list[Result]) -> tuple[list[Result], list[Result]]:
    """(succeeded, failed), each kept in the order given."""
    return [r for r in results if r.ok], [r for r in results if not r.ok]


def failure_kinds(results: list[Result]) -> dict[str, int]:
    """How many failures of each error class, e.g. {'TransientError': 1}."""
    return dict(Counter(type(r.error).__name__ for r in results if not r.ok))


def status(result: Result) -> str:
    return "ok" if result.ok else "failed"


def log_line(result: Result, when: datetime) -> str:
    """The result as one logparse line: `<timestamp> <LEVEL> fetch: <message>`."""
    stamp = when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if result.error is None:
        return f"{stamp} INFO fetch: job {result.job_id} ok"
    kind = type(result.error).__name__
    return (
        f"{stamp} ERROR fetch: job {result.job_id} failed {kind} {result.error.reason}"
    )
