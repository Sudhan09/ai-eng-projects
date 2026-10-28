# flowmap_playground

Type an input, press Run, and watch that exact input travel from START to END on the week's map. It isn't a test's run: it's your own.

```
python3 flowmap_playground/server.py
```

Open the link it prints (`http://127.0.0.1:8765/`). Pick the week in the project menu, pick what to run, type, press **Run** (or Enter). A few seconds later your run plays. It also stays in the run menu as `/v2/items/7 · 82 steps · ↩ 0 · {"url": …}`, so you can switch between inputs and compare them.

## What you can type

| Week | Run | Type, for example | What you'll see |
|---|---|---|---|
| W4 | python -m aiofetch | `/v2/items/7` | your settings, the client, one fetch, END `↩ 0` and the printed row |
| W4 | python -m aiofetch | `/items/1=503,503,200` | the fake answers 503, 503, then 200: three tries |
| W4 | client.get_item | `1500` | END `↩ ItemMissing` |
| W4 | client.get_item | `3007` | moved: a second fetch of `/v2/items/7`, END `↩ ItemFound` |
| W3 | client.fetch_many | `/items/1 /items/3=404` | two results, one of them the 404 |
| W2 | async-batch-fetcher | `--jobs 5 --fail-every 3` | 5 jobs in parallel lanes, every third one failing |
| W1 | logparse | `--level WARNING` (log lines on the next lines with Shift+Enter, or none for the sample log) | the pipeline counting what's kept |

- **`=` scripts the fake server:** `/items/1=503,503,200` means the fake answers that path 503, then 503, then 200. Words it knows, like `timeout`, work too.
- **END for `python -m …`:** the exit code (`↩ 0`, `1`, `2`) and the first printed line. The END box shows every printed line.
- **Too long:** a run over 5,000 events (e.g. `--jobs 300`) is refused, because it's too long to step through. Try a smaller input.

## How it works

1. The page sends your input to `server.py`, on this machine only.
2. The server records it with `flowmap_tests/tools/trace.py`, on the newest Part's code, through the week's driver (`drivers/w4.py`).
   - The driver plugs the fake server in, as your tests do. For `python -m aiofetch`, only the network under httpx is faked, so your settings, `make_client` and `HttpxTransport` all really run.
   - Only the driver's entry is recorded, as a hidden "you" frame. START is your first call, END its output.
3. The server rebuilds that week's map with `flowmap_tests/tools/build_project.py`, with your runs as a separate list. The page plays the new run.

**Shared, not copied:** the recorder, the scanner and the page all come from `flowmap_tests`. Your runs only add a run menu, the input box and the lines your runs took; the map's cards are the same as on the tests map.

## Safety

- The same rules as recording tests:
  - no network beyond this machine;
  - `*_API_KEY` / `*_TOKEN` removed and every proxy pointed at a closed port;
  - at most 90 seconds per run.
- Your code runs in an empty throwaway folder, so it never reads your real `.env`. W4 gets a fake key, `playground-not-a-real-key`.
- Your input is passed to the driver as text, never run as code.
- The server listens on 127.0.0.1 only. It answers only requests made to its own name, and runs only for its own page (a secret made at each start). So a website you visit can't trigger a run.

## Files

| Path | What it is |
|---|---|
| `server.py` | The local server: the page, the Run button, recording, keeping the last 20 runs per week |
| `drivers/w1.py` … `w4.py` | How your input reaches each week's code (`ENTRIES`: the label, the hint, and the function that runs it) |
| `drivers/_input.py` | Reads `path=answers` words |
| `tests/` | `test_playground.py` (a server in a throwaway folder, every week, the page in Chrome, every page guard), `run_in_page.mjs` (types into the real page) |
| `runs/`, `build/` | Your runs and the page: on your machine only, not in git and not synced |
| `PLAN.md` | The checklist this was built from |

Run the tests with `python3 -m unittest discover -s flowmap_playground/tests` (about a minute; needs Chrome and node for the page tests).

## A new week

Each week needs a driver once (about 15 lines), written when the week is added to the map: `drivers/w5.py`, with the week's entry point and its fake. Without a driver, the week has no input box. If a later Part changes an entry point, `tests/test_playground.py` fails and says which one.

## What could go wrong

| What you see | Why | What to do |
|---|---|---|
| The page says "too long to step through" | Over 5,000 events | A smaller input (fewer jobs, fewer paths) |
| "get_item takes item ids" | The input didn't fit the entry | Type what the box's hint shows |
| A new commit isn't in the playground | The page was built when the server started | Restart `server.py` (runs always use the newest Part) |
| The link doesn't open | The server isn't running, or another program has the port | `python3 flowmap_playground/server.py --port 8766` |
| The claude.ai map has no input box | That copy can't run Python | Use the local page |
