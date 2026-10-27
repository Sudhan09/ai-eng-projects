import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from aiofetch.storage import write_jsonl


@dataclass
class Counts:
    records: int
    malformed: int


def test_write_jsonl_writes_one_object_a_line_and_counts_them(tmp_path):
    path = tmp_path / "results.jsonl"
    assert write_jsonl(path, ({"n": n} for n in range(3))) == 3
    assert path.read_text() == '{"n": 0}\n{"n": 1}\n{"n": 2}\n'


def test_write_jsonl_encodes_paths_and_dataclasses(tmp_path):
    path = tmp_path / "out.jsonl"
    write_jsonl(path, [{"file": Path("data/a.bin"), "stats": Counts(3, 1)}])
    assert json.loads(path.read_text()) == {
        "file": "data/a.bin",
        "stats": {"records": 3, "malformed": 1},
    }


def test_anything_else_it_cannot_encode_is_a_type_error(tmp_path):
    with pytest.raises(TypeError, match="set"):
        write_jsonl(tmp_path / "out.jsonl", [{"ids": {1, 2}}])


# my own: an empty list writes an empty file and returns 0
def test_an_empty_list_writes_an_empty_file():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "empty.jsonl"
        assert write_jsonl(path, []) == 0
        assert path.read_text() == ""
