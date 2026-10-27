# async-batch-fetcher

Week 2: fetch a batch of jobs from a slow service, at most 20 at a time, and report how it went.

The input is a list of job ids. Each job is a question for a pretend service on your own machine (`MockServer`, 50 ms per answer). Every job comes back as a `Result` holding its payload or its error. The output is a report:

```console
$ uv run async-batch-fetcher --jobs 200 --fail-every 10 --timing
{
  "jobs": 200,
  "ok": 180,
  "failed": {"TransientError": 10, "PermanentError": 10},
  "checksums": 180,
  "peak_in_flight": 20,
  "orphaned_tasks": 0
}
took 0.72 s
```

| Part | What it adds | Where |
|---|---|---|
| 1 | One job over a socket, then jobs one by one | `client.fetch`, `run_serial` |
| 2 | All jobs at once | `run_gather` |
| 3 | Failures as values, live progress | `fetch_result`, `run_all`, `run_with_progress` |
| 4 | Never more than N in flight, a deadline per job, a stream that leaves no task behind | `Fetcher` |
| 5 | One owner for every task: a `TaskGroup`, checksums in a thread, a strict mode that stops at the first 404 | `guarded`, `run_group` |

Options: `--concurrency`, `--delay`, `--fail-every`, `--timeout`, `--strict` (the first 404 stops the batch), `--log FILE` (one logparse line per job), `--timing`.

Tests: `uv run pytest`. Lint: `uv run ruff check && uv run ruff format --check`.
