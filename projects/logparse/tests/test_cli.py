import io
import json
import sys
from pathlib import Path

import pytest

from logparse.cli import main

SAMPLE = str(Path(__file__).parent / "fixtures" / "sample.log")


def run_json(capsys, *args):
    assert main([*args, "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def test_no_filters_counts_every_good_line(capsys):
    report = run_json(capsys, SAMPLE)
    assert report["total"] == 6
    assert report["error_count"] == 1  # the malformed line


def test_level_is_a_floor(capsys):
    report = run_json(capsys, SAMPLE, "--level", "WARNING")
    assert report["by_level"] == {"WARNING": 1, "ERROR": 2, "CRITICAL": 1}


def test_pattern_keeps_matching_messages(capsys):
    report = run_json(capsys, SAMPLE, "--pattern", "connection")
    assert report["by_level"] == {"ERROR": 2}


def test_timing_goes_to_stderr(capsys):
    assert main([SAMPLE, "--timing"]) == 0
    out, err = capsys.readouterr()
    assert "total    6" in out
    assert "took" in err
    assert "took" not in out


def test_dash_reads_standard_input(monkeypatch, capsys):
    text = Path(SAMPLE).read_text(encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))
    report = run_json(capsys, "-")
    assert report["total"] == 6


def test_missing_file_gives_clean_message(tmp_path, capsys):
    missing = str(tmp_path / "nope.log")
    assert main([missing]) == 2
    out, err = capsys.readouterr()
    assert out == ""
    assert err.startswith("logparse:")
    assert "nope.log" in err
    assert "Traceback" not in err


def test_bad_regex_exits_with_usage_error(capsys):
    with pytest.raises(SystemExit) as info:
        main([SAMPLE, "--pattern", "("])
    assert info.value.code == 2
    assert "bad --pattern" in capsys.readouterr().err
