"""Week 1 (logparse): each Part's entry, and suggested inputs that together reach every component of that Part.

Settings go on the first line, log lines below it. With no log lines, the sample log below is used.
Your project's code is imported inside each entry, so this file loads at any Part.
"""

import io
import shlex
import sys
from pathlib import Path

from _input import last, options, with_call

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


# your tests' values -> the words you'd type (suggest.py)
def line_typed(a, before):
    return a["line"] if isinstance(a.get("line"), str) and a["line"].strip() and "\n" not in a["line"] else None


def listed(name, values):
    ok = isinstance(values, list) and values and all(isinstance(v, str) and v and not set(v) & set(" ,=") for v in values)
    return f"{name}={','.join(values)}" if ok else ""


def lists_typed(a, before):
    return " ".join(w for w in (listed("levels", a.get("levels")), listed("patterns", a.get("patterns"))) if w) or None


def config_typed(a, before):  # pipeline.run: the ParserConfig the test made just before
    made = last(before, "config.ParserConfig.from_lists")
    return lists_typed(made, before) if made else None


def level_typed(a, before):
    level = (a.get("min_level") or {}).get("@enum", "") if isinstance(a.get("min_level"), dict) else ""
    return f"level={level.split('.')[-1]}" if level else None


def pattern_typed(a, before):
    return listed("pattern", [a.get("pattern")]) or None


def argv_typed(stdin):
    """cli.main's arguments without the log file (the sample log stands in for your test's file)."""
    def typed(a, before):
        argv = a.get("argv")
        if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv) or ("-" in argv) != stdin:
            return None
        flags = [x for x in argv if x != "-" and "/" not in x and not x.endswith((".log", ".txt", ".jsonl"))]
        return shlex.join(flags) if flags else None
    return typed


PARSE = {"label": "parse_line", "hint": "a log line per line, e.g. 2026-10-02T09:15:01Z ERROR db: connection refused", "run": run_parse,
         "from": {"record.parse_line": line_typed}}
CONFIG = {"label": "ParserConfig + parse_line", "hint": "levels=ERROR,WARNING patterns=refused   (log lines below, or none for a sample)", "run": run_config,
          "from": {"config.ParserConfig.from_lists": lists_typed}}
FILTERS = {"label": "the filters", "hint": "level=WARNING pattern=refused   (log lines below, or none for a sample)", "run": run_filters,
           "from": {"filters.level_at_least": level_typed, "filters.matches": pattern_typed}}
PIPELINE = {"label": "pipeline.run", "hint": "levels=ERROR,WARNING patterns=refused   (log lines below, or none for a sample)", "run": run_pipeline,
            "from": {"pipeline.run": config_typed}}
CLI = {"label": "logparse (a file)", "hint": "--level WARNING --json   (log lines below, or none for a sample)", "run": run_cli,
       "from": {"cli.main": argv_typed(stdin=False)}}
CLI_STDIN = {"label": "logparse (standard input)", "hint": "--level WARNING   (log lines below, or none for a sample)", "run": run_cli_stdin,
             "from": {"cli.main": argv_typed(stdin=True)}}

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
with_call(PARTS, 'record.parse_line("2026-10-02T09:15:01Z ERROR db: down")')
