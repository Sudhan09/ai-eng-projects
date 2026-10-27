import pytest

from logparse.filters import (
    all_of,
    compiled_pattern,
    level_at_least,
    matches,
    render,
    timed,
)
from logparse.record import LogLevel, parse_line

ERR = parse_line("2026-10-02T09:15:04Z ERROR db: connection refused")
INFO = parse_line("2026-10-02T09:15:03Z INFO auth: user login ok")


def test_level_at_least():
    keep = level_at_least(LogLevel.WARNING)
    assert keep(ERR) and not keep(INFO)


def test_filters_made_in_a_loop_stay_different():
    filters = [level_at_least(lvl) for lvl in (LogLevel.INFO, LogLevel.ERROR)]
    assert filters[0](INFO) and not filters[1](INFO)


def test_all_of_needs_every_filter():
    keep = all_of(level_at_least(LogLevel.ERROR), matches("refused"))
    assert keep(ERR) and not keep(INFO)
    assert all_of()(INFO)


def test_timed_keeps_name_doc_and_result(capsys):
    @timed
    def double(x):
        """Return twice x."""
        return 2 * x

    assert double(4) == 8
    assert (double.__name__, double.__doc__) == ("double", "Return twice x.")
    assert "double took" in capsys.readouterr().err


def test_compiled_pattern_uses_the_cache():
    compiled_pattern.cache_clear()
    compiled_pattern("ref.*d")
    compiled_pattern("ref.*d")
    assert compiled_pattern.cache_info().hits == 1


def test_render_picks_by_type():
    assert render(ERR) == "ERROR db: connection refused"
    assert render("raw text") == "raw text"


def test_matches_word_in_middle():
    rec = parse_line("2026-10-02T09:15:04Z ERROR db: the connection was refused today")
    assert matches("refused")(rec)


def test_timed_prints_even_when_it_crashes(capsys):
    @timed
    def boom():
        raise ValueError("oops")

    with pytest.raises(ValueError):
        boom()
    assert "boom took" in capsys.readouterr().err
