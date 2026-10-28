"""Week 1 (logparse): your arguments on the first line, your log lines below it (none: the sample log)."""

import io
import shlex
import sys
from pathlib import Path

import logparse
from logparse.cli import main

SAMPLE = Path(logparse.__file__).parents[2] / "tests" / "fixtures" / "sample.log"


def run_cli(text):
    args, _, lines = text.partition("\n")
    sys.stdin = io.StringIO(lines if lines.strip() else SAMPLE.read_text())
    return main([*shlex.split(args), "-"])  # "-": read the log from standard input


ENTRIES = {"cli": {"label": "logparse", "hint": "--level WARNING   (log lines on the next lines, or none for the sample log)", "run": run_cli}}
