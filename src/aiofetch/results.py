from dataclasses import dataclass


@dataclass(frozen=True)
class Result:
    url: str
    value: object = None
    error: object = None
    seconds: float = 0.0

    @property
    def ok(self):
        return self.error is None


def percentile(values, pct):
    ordered = sorted(values)
    rank = round(pct / 100 * len(ordered))
    if rank < 1:
        rank = 1
    return ordered[rank - 1]
