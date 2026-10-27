import pytest

from logparse.record import LogLevel, LogRecord, parse_line

LINE = "2026-10-02T09:15:03Z INFO auth: user login ok"


def test_parse_line_fields():
    rec = parse_line(LINE)
    assert isinstance(rec, LogRecord)
    assert rec.timestamp == "2026-10-02T09:15:03Z"
    assert rec.level is LogLevel.INFO
    assert (rec.component, rec.message) == ("auth", "user login ok")


def test_equal_records_collapse_in_a_set():
    a, b = parse_line(LINE), parse_line(LINE)
    assert a == b
    assert a is not b
    assert len({a, b}) == 1


def test_two_faces():
    rec = parse_line(LINE)
    assert repr(rec).startswith("LogRecord(")
    assert "user login ok" in repr(rec)
    assert str(rec) == "INFO auth: user login ok"


def test_levels_have_an_order():
    assert LogLevel.DEBUG.value < LogLevel.INFO.value < LogLevel.CRITICAL.value


def test_bad_line_raises_value_error():
    with pytest.raises(ValueError):
        parse_line("garbage line")


def test_reads_a_real_file(tmp_path):
    log = tmp_path / "app.log"
    log.write_text(LINE + "\n", encoding="utf-8")
    first = log.read_text(encoding="utf-8").splitlines()[0]
    assert parse_line(first).level is LogLevel.INFO


def test_different_message_not_equal():
    a = parse_line(LINE)
    b = parse_line("2026-10-02T09:15:03Z INFO auth: user login failed")
    assert a != b


def test_record_works_as_dict_key():
    a, b = parse_line(LINE), parse_line(LINE)
    d = {a: 1}
    assert d[b] == 1
