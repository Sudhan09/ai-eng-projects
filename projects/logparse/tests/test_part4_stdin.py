import io
import sys

from logparse.config import ParserConfig
from logparse.pipeline import run

LINES = [
    "2026-10-02T09:15:03Z INFO auth: user login ok",
    "2026-10-02T09:15:04Z ERROR db: connection refused",
    "garbage line",
    "2026-10-02T09:16:10Z WARNING cache: hit rate low",
]


def test_standard_input_is_read_once(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(LINES) + "\n"))
    report = run(["-"], ParserConfig())
    assert report["total"] == 3
    assert report["by_level"]["ERROR"] == 1
    assert report["per_minute"]["2026-10-02T09:15"] == 2
