# logparse

`logparse` reads log files line by line (it streams, so even a 2 GB file uses
very little memory) and reports how many lines there are per level and per
minute. You can filter by level and by a regex on the message.

Each log line looks like this:

```
2026-10-02T09:15:04Z ERROR db: connection refused
```

Lines that don't fit that shape are counted as errors, not crashes.

## Install

You need [uv](https://docs.astral.sh/uv/) and Python 3.14.

```bash
git clone https://github.com/Sudhan09/logparse.git
cd logparse
uv sync
```

## Usage

```bash
# count every line in one or more files
uv run logparse app.log other.log

# keep WARNING and everything above it (ERROR, CRITICAL)
uv run logparse app.log --level WARNING

# keep only lines whose message matches a regex
uv run logparse app.log --pattern "timeout|refused"

# print the full report (per-minute counts, bad lines) as JSON
uv run logparse app.log --json

# print how long the run took (goes to stderr)
uv run logparse app.log --timing

# read from standard input with -
cat app.log | uv run logparse -
```

A missing file or a bad `--pattern` prints a one-line message and exits with
code 2. Run `uv run logparse --help` to see every option.

If a file `app.log.meta.json` sits next to `app.log` and contains a
`"source"` key, the JSON report includes it under `"sources"`.

## Run the tests

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```
