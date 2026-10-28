"""Week 1 (logparse): each Part's entry, and suggested inputs that together reach every component of that Part.

Settings go on the first line, log lines below it. With no log lines, the sample log below is used.
Your project's code is imported inside each entry, so this file loads at any Part.
"""

import io
import shlex
import sys
from pathlib import Path

from _input import options

SAMPLE = """2026-10-02T09:15:01Z DEBUG cache: warming up
2026-10-02T09:15:02Z INFO auth: user login ok
2026-10-02T09:15:03Z WARNING cache: hit rate low
2026-10-02T09:16:10Z ERROR db: connection refused
2026-10-02T09:16:12Z ERROR db: connection refused again"""


def split(text):
    """(the first line: settings, the log lines below it or the sample log)"""
    first, _, lines = text.partition("\n")
    return first, (lines if lines.strip() else SAMPLE).splitlines()


def records(lines):
    """Each line through parse_line; a line it refuses is left out (the refusal is still on the map)."""
    from logparse.record import parse_line
    out = []
    for line in lines:
        try:
            out.append(parse_line(line))
        except (ValueError, KeyError):
            pass
    return out


def config(first):
    from logparse.config import ParserConfig
    _, o = options(first, "levels", "patterns")
    return ParserConfig.from_lists(levels=o["levels"].split(",") if "levels" in o else None,
                                   patterns=o["patterns"].split(",") if "patterns" in o else None)


def run_parse(text):  # Part 1: every line is a log line
    from logparse.record import parse_line
    return [parse_line(line) for line in text.splitlines() if line.strip()]


def run_config(text):  # Part 2
    first, lines = split(text)
    cfg = config(first)
    return {"config": cfg, "kept": [r for r in records(lines) if r.level in cfg.levels]}


def run_filters(text):  # Part 3
    from logparse.config import ParserConfig
    from logparse.filters import all_of, level_at_least, matches
    from logparse.record import LogLevel
    first, lines = split(text)
    _, o = options(first, "level", "pattern")
    cfg = ParserConfig.from_lists(patterns=[o["pattern"]] if "pattern" in o else None)
    checks = [matches(p) for p in cfg.patterns] + ([level_at_least(LogLevel[o["level"]])] if "level" in o else [])
    keep = all_of(*checks)
    return {"kept": [r for r in records(lines) if keep(r)]}


def run_pipeline(text):  # Part 4: the log is written to a file, as pipeline.run reads files
    from logparse.pipeline import run
    first, lines = split(text)
    Path("logs.txt").write_text("\n".join(lines) + "\n")
    return run(["logs.txt"], config(first))


def run_cli(text):  # Part 5: the command, reading the log from a file
    from logparse.cli import main
    first, lines = split(text)
    Path("logs.txt").write_text("\n".join(lines) + "\n")
    return main([*shlex.split(first), "logs.txt"])


def run_cli_stdin(text):  # Part 5: the same command, reading standard input ("-")
    from logparse.cli import main
    first, lines = split(text)
    sys.stdin = io.StringIO("\n".join(lines) + "\n")
    return main([*shlex.split(first), "-"])


PARSE = {"label": "parse_line", "hint": "a log line per line, e.g. 2026-10-02T09:15:01Z ERROR db: connection refused", "run": run_parse}
CONFIG = {"label": "ParserConfig + parse_line", "hint": "levels=ERROR,WARNING patterns=refused   (log lines below, or none for a sample)", "run": run_config}
FILTERS = {"label": "the filters", "hint": "level=WARNING pattern=refused   (log lines below, or none for a sample)", "run": run_filters}
PIPELINE = {"label": "pipeline.run", "hint": "levels=ERROR,WARNING patterns=refused   (log lines below, or none for a sample)", "run": run_pipeline}
CLI = {"label": "logparse (a file)", "hint": "--level WARNING --json   (log lines below, or none for a sample)", "run": run_cli}
CLI_STDIN = {"label": "logparse (standard input)", "hint": "--level WARNING   (log lines below, or none for a sample)", "run": run_cli_stdin}

PARTS = {
    "1": {"entries": {"parse": PARSE}, "scenarios": [
        ("parse", "2026-10-02T09:15:01Z ERROR db: connection refused", "good", "A log line becomes a LogRecord"),
        ("parse", "this line is not a log line", "bad", "A line that isn't a log line is refused"),
        ("parse", "2026-10-02T09:15:01Z EROR db: typo in the level", "more", "An unknown level is refused"),
    ]},
    "2": {"entries": {"config": CONFIG}, "scenarios": [
        ("config", "levels=ERROR,WARNING", "good", "Keep only the ERROR and WARNING lines"),
        ("config", "levels=EROR", "bad", "A misspelled level stops the config"),
    ]},
    "3": {"entries": {"filters": FILTERS}, "scenarios": [
        ("filters", "level=WARNING", "good", "WARNING and above pass the filter"),
        ("filters", "pattern=[", "bad", "A broken pattern is refused"),
        ("filters", "level=INFO pattern=refused", "more", "Both filters at once: only the refused lines"),
    ]},
    "4": {"entries": {"pipeline": PIPELINE}, "scenarios": [
        ("pipeline", "levels=ERROR,WARNING", "good", "The pipeline counts what it keeps, per level and minute"),
        ("pipeline", "levels=EROR", "bad", "A misspelled level stops the run"),
        ("pipeline", "patterns=cache", "more", "Only the lines about the cache"),
    ]},
    "5": {"entries": {"cli": CLI, "cli_stdin": CLI_STDIN}, "scenarios": [
        ("cli", "--level WARNING", "good", "The command counts per level, reading a file"),
        ("cli", "--level BOGUS", "bad", "An unknown level: the command stops with exit 2"),
        ("cli", "--json\n2026-10-02T09:15:03Z WARNING cache: hit rate low\nthis line is not a log line", "more", "A broken line is skipped and counted"),
        ("cli_stdin", "--level ERROR", "more", "The same command, reading standard input"),
    ]},
}
