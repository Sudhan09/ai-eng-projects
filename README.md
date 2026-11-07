# AI engineering projects

My week-by-week projects from an AI engineering course, one folder per project, each with its full commit history ("Week N Part X: ..." commits, then "feat(w5p1): ..." from Week 5).

| Folder | Week | What it is |
|---|---|---|
| `projects/logparse` | 1 | stream a log file bigger than RAM |
| `projects/async-batch-fetcher` | 2 | a thousand async jobs at once, with limits and clean cancellation |
| `projects/aiofetch` | 3-4 | an HTTP client that survives a flaky API (retries, rate limits, circuit breaker), then typed, validated with Pydantic, streamed to JSONL and configured from the environment |
| `projects/stream-svc` | 5 | a streaming LLM service: tokens over SSE, a load harness, request ids, telemetry and clean errors |
| `projects/interview-notes` | - | notes |
| `flowmap_tests` | - | an animated map of each project's call flow, built from recorded test runs. Open `flowmap_tests/build/flowmap.html` |
| `flowmap_playground` | - | type your own input and watch it travel through each week's code, on your own machine |

## Keeping it in sync

The projects are developed in their own repos. `./sync.sh` pulls each project's new commits in (history kept) and refreshes the flowmap and notes, then commits.
