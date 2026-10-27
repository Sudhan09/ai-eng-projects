import json

from logparse.config import ParserConfig
from logparse.pipeline import jsonl_chunks, keep, parse, read_lines, run
from logparse.record import LogLevel

LINES = [
    "2026-10-02T09:15:03Z INFO auth: user login ok",
    "2026-10-02T09:15:04Z ERROR db: connection refused",
    "garbage line",
    "2026-10-02T09:16:10Z WARNING cache: hit rate low",
]


def write_log(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return str(log)


def test_stages_are_lazy():
    records = parse(iter(LINES))
    assert iter(records) is records
    assert next(records).level is LogLevel.INFO


def test_keep_filters():
    kept = keep(parse(LINES), lambda r: r.level.value >= LogLevel.WARNING.value)
    assert [r.level for r in kept] == [LogLevel.ERROR, LogLevel.WARNING]


def test_read_lines_strips_newlines(tmp_path):
    assert next(read_lines(write_log(tmp_path))) == LINES[0]


def test_run_counts_in_one_report(tmp_path):
    report = run([write_log(tmp_path)], ParserConfig())
    assert report["total"] == 3
    assert report["by_level"] == {"INFO": 1, "ERROR": 1, "WARNING": 1}
    assert report["per_minute"] == {"2026-10-02T09:15": 2, "2026-10-02T09:16": 1}


def test_head_stops_early(tmp_path):
    assert run([write_log(tmp_path)], ParserConfig(), head=1)["total"] == 1


def test_jsonl_chunks_come_in_batches():
    chunks = list(jsonl_chunks(parse(LINES), size=2))
    assert len(chunks) == 2
    rows = [json.loads(line) for chunk in chunks for line in chunk.splitlines()]
    assert [row["level"] for row in rows] == ["INFO", "ERROR", "WARNING"]


def test_two_files_read_in_order(tmp_path):
    a = tmp_path / "a.log"
    b = tmp_path / "b.log"
    a.write_text("2026-10-02T09:15:03Z INFO auth: ok\n", encoding="utf-8")
    b.write_text("2026-10-02T09:16:03Z ERROR db: refused\n", encoding="utf-8")
    report = run([str(a), str(b)], ParserConfig())
    assert report["total"] == 2


def test_pattern_keeps_only_matching(tmp_path):
    report = run([write_log(tmp_path)], ParserConfig.from_lists(patterns=["refused"]))
    assert report["total"] == 1
    assert report["by_level"] == {"ERROR": 1}
