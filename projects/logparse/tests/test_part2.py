import dataclasses

import pytest

from logparse.config import ParserConfig
from logparse.record import LogLevel, parse_line

ERRORS = frozenset({LogLevel.ERROR, LogLevel.CRITICAL})


def test_config_cannot_change():
    cfg = ParserConfig(patterns=("timeout",))
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.patterns = ("refused",)


def test_merge_returns_a_new_config():
    a = ParserConfig(levels=ERRORS, patterns=("timeout",))
    b = ParserConfig(
        levels=frozenset({LogLevel.ERROR}), patterns=("refused", "timeout")
    )
    merged = a.merge(b)
    assert merged is not a and merged is not b
    assert merged.levels == frozenset({LogLevel.ERROR})
    assert merged.patterns == ("timeout", "refused")
    assert a.patterns == ("timeout",) and b.patterns == ("refused", "timeout")


def test_constructor_copies_mutable_input():
    patterns = ["timeout"]
    cfg = ParserConfig(levels={LogLevel.ERROR}, patterns=patterns)
    patterns.append("refused")
    assert cfg.patterns == ("timeout",)
    assert isinstance(cfg.levels, frozenset)


def test_merge_drops_repeats_from_both_sides():
    merged = ParserConfig(patterns=("x", "x")).merge(ParserConfig(patterns=("y", "x")))
    assert merged.patterns == ("x", "y")


def test_from_lists_copies_its_input():
    patterns = ["timeout"]
    cfg = ParserConfig.from_lists(patterns=patterns)
    patterns.append("refused")
    assert cfg.patterns == ("timeout",)


def test_from_lists_defaults_are_fresh():
    assert ParserConfig.from_lists() == ParserConfig()
    assert ParserConfig.from_lists(levels=["ERROR"]).levels == {LogLevel.ERROR}


def test_records_are_frozen_too():
    rec = parse_line("2026-10-02T09:15:03Z INFO auth: user login ok")
    with pytest.raises(dataclasses.FrozenInstanceError):
        rec.message = "edited"


def test_merge_with_itself_changes_nothing():
    cfg = ParserConfig.from_lists(levels=["ERROR"], patterns=["timeout"])
    assert cfg.merge(cfg) == cfg


def test_from_lists_unknown_fails_loudly():
    with pytest.raises(KeyError):
        ParserConfig.from_lists(levels=["EROR"])
