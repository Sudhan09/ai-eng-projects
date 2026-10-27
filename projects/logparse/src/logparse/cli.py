import argparse
import json
import re
import sys

from logparse.config import ParserConfig
from logparse.filters import timed
from logparse.pipeline import run
from logparse.record import LogLevel

LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="logparse",
        description="Count log lines by level and minute.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="log files to read; use - to read from standard input",
    )
    parser.add_argument(
        "--level",
        choices=LEVELS,
        help="keep only this level and the levels above it",
    )
    parser.add_argument(
        "--pattern",
        help="keep only lines whose message matches this regex",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the full report as JSON",
    )
    parser.add_argument(
        "--timing",
        action="store_true",
        help="print how long the run took to stderr",
    )
    return parser


def make_config(args: argparse.Namespace) -> ParserConfig:
    levels = None
    if args.level:
        floor = LogLevel[args.level].value
        levels = [lv.name for lv in LogLevel if lv.value >= floor]
    patterns = [args.pattern] if args.pattern else None
    return ParserConfig.from_lists(levels=levels, patterns=patterns)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.pattern is not None:
        try:
            re.compile(args.pattern)
        except re.error as exc:
            parser.error(f"bad --pattern {args.pattern!r}: {exc}")
    config = make_config(args)
    do_run = timed(run) if args.timing else run
    try:
        report = do_run(args.paths, config)
    except OSError as exc:
        print(f"logparse: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)
    return 0


def print_report(report: dict) -> None:
    print(f"total    {report['total']}")
    for level, count in report["by_level"].items():
        print(f"{level:<8} {count}")
    print(f"errors   {report['error_count']}")


if __name__ == "__main__":
    sys.exit(main())
