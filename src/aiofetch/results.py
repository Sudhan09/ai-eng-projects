from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Result[T]:
    url: str
    value: T | None = None
    error: object = None
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None


def percentile(values: Iterable[float], pct: float) -> float:
    ordered = sorted(values)
    rank = round(pct / 100 * len(ordered))
    if rank < 1:
        rank = 1
    return ordered[rank - 1]
