import json

import pytest

from logparse.cli import main
from logparse.config import ParserConfig
from logparse.errors import MalformedLineError, ParseError, UnknownLevelError
from logparse.files import open_log
from logparse.pipeline import run
from logparse.record import parse_line


def test_bad_lines_raise_typed_chained_errors():
    with pytest.raises(MalformedLineError) as info:
        parse_line("garbage line")
    assert isinstance(info.value, ParseError)
    assert info.value.__cause__ is not None
    with pytest.raises(UnknownLevelError):
        parse_line("2026-10-02T09:16:10Z LOUD api: what is this")


def test_errors_are_never_transient():
    assert ParseError.transient is False


def test_run_reports_every_bad_line(tmp_path):
    log = tmp_path / "bad.log"
    log.write_text(
        "half a line\n2026-10-02T09:15:03Z INFO a: fine\nbad\n", encoding="utf-8"
    )
    report = run([str(log)], ParserConfig())
    assert report["total"] == 1
    assert [e["line_no"] for e in report["errors"]] == [1, 3]
    assert all(
        e["error"] == "MalformedLineError" and e["cause"] for e in report["errors"]
    )


def test_error_report_stays_bounded(tmp_path):
    log = tmp_path / "bad.log"
    log.write_text("bad\n" * 50, encoding="utf-8")
    report = run([str(log)], ParserConfig(), max_errors=10)
    assert report["error_count"] == 50
    assert len(report["errors"]) == 10


def test_open_log_closes_even_on_error(tmp_path):
    log = tmp_path / "a.log"
    log.write_text("x\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        with open_log(log) as handle:
            raise RuntimeError("boom")
    assert handle.closed


def test_cli_prints_json(tmp_path, capsys):
    log = tmp_path / "a.log"
    log.write_text(
        "2026-10-02T09:15:03Z INFO a: fine\n2026-10-02T09:15:04Z ERROR db: refused\n",
        encoding="utf-8",
    )
    assert main([str(log), "--level", "ERROR", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["by_level"] == {"ERROR": 1}
