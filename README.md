# AI engineering projects

My week-by-week projects from an AI engineering course, one folder per project, each with its full commit history ("Week N Part X: ..." commits).

| Folder | Week | What it is |
|---|---|---|
| `projects/logparse` | 1 | stream a log file bigger than RAM |
| `projects/async-batch-fetcher` | 2 | a thousand async jobs at once, with limits and clean cancellation |
| `projects/aiofetch` | 3-4 | an HTTP client that survives a flaky API (retries, rate limits, circuit breaker), then typed, validated with Pydantic, streamed to JSONL and configured from the environment |
| `projects/interview-notes` | - | notes |
| `flowmap` | - | an animated map of each project's call flow, built from recorded test runs. Open `flowmap/build/flowmap.html` |

## Keeping it in sync

The projects are developed in their own repos. `./sync.sh` pulls each project's new commits in (history kept) and refreshes the flowmap and notes, then commits.
