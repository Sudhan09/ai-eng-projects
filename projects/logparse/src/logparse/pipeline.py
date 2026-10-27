import itertools
import json
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from contextlib import ExitStack

from logparse.config import ParserConfig
from logparse.errors import ParseError
from logparse.files import open_log
from logparse.filters import all_of, matches
from logparse.record import LogRecord, parse_line


def read_lines(path: str) -> Iterator[str]:
    if path == "-":
        yield from lines_from(sys.stdin)
        return
    with open_log(path) as f:
        yield from lines_from(f)


def lines_from(f: Iterable[str]) -> Iterator[str]:
    for line in f:
        yield line.rstrip("\n")


def parse(
    lines: Iterable[str], errors: "CappedList | None" = None, file: str = "-"
) -> Iterator[LogRecord]:
    for line_no, line in enumerate(lines, start=1):
        try:
            record = parse_line(line)
        except ParseError as exc:
            if errors is not None:
                errors.append(
                    {
                        "file": file,
                        "line_no": line_no,
                        "error": type(exc).__name__,
                        "cause": str(exc.__cause__),
                    }
                )
        else:
            yield record


def keep(
    records: Iterable[LogRecord], pred: Callable[[LogRecord], bool]
) -> Iterator[LogRecord]:
    for r in records:
        if pred(r):
            yield r


def jsonl_chunks(records: Iterable[LogRecord], size: int = 1000) -> Iterator[str]:
    for batch in itertools.batched(records, size, strict=False):
        lines = []
        for r in batch:
            row = {
                "timestamp": r.timestamp,
                "level": r.level.name,
                "component": r.component,
                "message": r.message,
            }
            lines.append(json.dumps(row))
        yield "\n".join(lines)


def run(
    paths: list[str],
    config: ParserConfig,
    head: int | None = None,
    max_errors: int = 1000,
) -> dict:
    errors = CappedList(max_errors)
    with ExitStack() as stack:
        streams = []
        sources = {}
        for p in paths:
            f = sys.stdin if p == "-" else stack.enter_context(open_log(p))
            streams.append(parse(lines_from(f), errors, p))
            source = read_source(p) if p != "-" else None
            if source is not None:
                sources[p] = source
        records = itertools.chain.from_iterable(streams)
        preds = [lambda r: r.level in config.levels]

        preds += [matches(p) for p in config.patterns]
        kept = keep(records, all_of(*preds))
        if head is not None:
            kept = itertools.islice(kept, head)

        by_level = Counter()
        per_minute = {}
        for minute, group in itertools.groupby(kept, key=lambda r: r.timestamp[:16]):
            count = 0
            for r in group:
                by_level[r.level.name] += 1
                count += 1
            per_minute[minute] = per_minute.get(minute, 0) + count
        report = {
            "total": sum(by_level.values()),
            "by_level": dict(by_level),
            "per_minute": per_minute,
            "error_count": errors.count,
            "errors": errors.items,
        }
        if sources:
            report["sources"] = sources
        return report


def read_source(path: str) -> str | None:
    try:
        with open(f"{path}.meta.json", encoding="utf-8") as f:
            return json.load(f)["source"]
    except FileNotFoundError, KeyError, json.JSONDecodeError:
        return None


class CappedList:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.items = []
        self.count = 0

    def append(self, item: dict) -> None:
        self.count += 1
        if len(self.items) < self.limit:
            self.items.append(item)
