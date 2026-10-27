import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import TypeIs


def encode(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"can't encode {type(value).__name__} as JSON")


def write_jsonl(path: Path, records: Iterable[Mapping[str, object]]) -> int:
    count = 0
    with path.open("w") as sink:
        for record in records:
            sink.write(json.dumps(record, default=encode) + "\n")
            count += 1
    return count


@dataclass
class ReadStats:
    records: int = 0
    malformed: int = 0


def is_json_object(value: object) -> TypeIs[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    for key in value:
        if not isinstance(key, str):
            return False
    return True


def read_jsonl(path: Path, stats: ReadStats | None = None) -> Iterator[dict[str, object]]:
    if stats is None:
        stats = ReadStats()
    with path.open() as source:
        for line in source:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                stats.malformed += 1
                continue
            if not is_json_object(value):
                stats.malformed += 1
                continue
            stats.records += 1
            yield value
