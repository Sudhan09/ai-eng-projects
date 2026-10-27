from collections.abc import Iterable
from dataclasses import dataclass
from typing import Required, TypedDict


class ResultRow(TypedDict, total=False):
    url: Required[str]
    seconds: Required[float]
    value: object
    error: str


@dataclass(frozen=True)
class Result[T]:
    url: str
    value: T | None = None
    error: object = None
    seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.value is not None and self.error is not None:
            raise ValueError("a Result holds a value or an error, not both")

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_row(self) -> ResultRow:
        row: ResultRow = {"url": self.url, "seconds": round(self.seconds, 6)}
        if self.error is not None:
            row["error"] = str(self.error)
        else:
            row["value"] = self.value
        return row


def percentile(values: Iterable[float], pct: float) -> float:
    ordered = sorted(values)
    rank = round(pct / 100 * len(ordered))
    if rank < 1:
        rank = 1
    return ordered[rank - 1]
