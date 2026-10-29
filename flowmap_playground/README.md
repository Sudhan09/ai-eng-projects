# flowmap_playground

**Start with [the handbook](../flowmap_tests/HANDBOOK.md):** what to do each week, how both maps stay up to date, and every rule.

Type an input, press Run, and watch that exact input travel from START to END on the week's map. It isn't a test's run: it's your own.

```
python3 flowmap_playground/server.py
```

Open the link it prints (`http://127.0.0.1:8765/`).

1. Pick the week in the project menu, and a Part in the top bar. The box always runs that Part's code.
2. Pick a suggestion from **Try:** (it fills the box), or pick what to run and type your own.
3. Press **Run** (or Enter). A few seconds later your run plays.

The run also stays in that Part's run menu as `/v2/items/7 · 82 steps · ↩ 0 · {"url": …}`, so you can switch between inputs and compare them. A Part with nothing to run says so ("Nothing to run at Part 2"), and it never uses another Part's code instead.

## What you can type

**Each Part has its own entries,** because entry points change: W3 Part 1 only has `make_client` and `get_json`, while `fetch_many` arrives in Part 3. They live in the week's driver (`drivers/w4.py`, its `PARTS` table). A new Part without a row of its own borrows the row before it.

**Its Try: suggestions come from its tests,** made again after each commit:

```
test_get_item_returns_the_shape_the_server_sent      (W4 Part 3)
└─ client.get_item(item_id = 1500)  →  ItemMissing
      ↓ the get_item entry's "from" rule
Try: "1500"     Get item returns the shape the server sent: ↩ ItemMissing
```

- `harvest.py` runs the Part's tests once and notes the values each of your functions got, and how it ended.
- Each entry's `from` rule turns those values into the words you'd type, using what the test set up just before (its fake's script, `/items/2=404`; its client's `rpm=`).
- A function the Part added, whose tests gave it only plain values, gets the **call** entry: `storage.is_json_object({"url": "/items/1"})`.
- `suggest.py` keeps up to 4. The Part's new tests come first: one that ends fine, one that raises or exits non-zero, then different endings. Each is played on the Part's code before it's shown.
- The driver's own suggestions (a good input, a bad one and up to two more, which together reach every component that Part has) are shown only when the tests give none.

**"a function of yours"** is in every Part: type any function of your package with plain values, like `record.parse_line("2026-10-02T09:15:01Z ERROR db: down")`. The values are read as data (text, numbers, lists, dicts, True/False/None), and only your package's functions can be called.

Some examples, on each week's last Part:

| Week | Run | Type, for example | What you'll see |
|---|---|---|---|
| W4 | python -m aiofetch | `/v2/items/7` | your settings, the client, one fetch, END `↩ 0` and the printed row |
| W4 | python -m aiofetch | `/items/1=503,503,200` | the fake answers 503, 503, then 200: three tries |
| W4 | client.get_item | `1500` | END `↩ ItemMissing` |
| W4 | client.get_item | `3007` | moved: a second fetch of `/v2/items/7`, END `↩ ItemFound` |
| W4 | fetch → write → read jsonl | `/items/1 /items/2` | fetch_many, to_row, write_jsonl, read_jsonl; END `↩ {rows, stats}`: the rows read back and `ReadStats(records=2, malformed=0)` |
| W4 | fetch → write → read jsonl | `/items/1 /items/2 torn` | the same, with half a line added to the file first: the rows still come back, and `malformed=1` |
| W3 | client.fetch_many | `/items/1 /items/3=404` | two results, one of them the 404 |
| W2 | async-batch-fetcher | `--jobs 5 --fail-every 3` | 5 jobs in parallel lanes, every third one failing |
| W1 | logparse | `--level WARNING` (log lines on the next lines with Shift+Enter, or none for the sample log) | the pipeline counting what's kept |

- **`=` scripts the fake server:** `/items/1=503,503,200` means the fake answers that path 503, then 503, then 200. Words it knows, like `timeout`, work too.
- **END for `python -m …`:** the exit code (`↩ 0`, `1`, `2`) and the first printed line. The END box shows every printed line.
- **END for an entry that gives back several things** (like `jsonl`): its names (`↩ {rows, stats}`). The END box shows each one in full. A driver entry does this by returning a dict.
- **Too long:** a run over 5,000 events (e.g. `--jobs 300`) is refused, because it's too long to step through. Try a smaller input.

## How it works

1. The page sends your input to `server.py`, on this machine only.
2. The server records it with `flowmap_tests/tools/trace.py`, on the code of the Part you picked (`flowmap_tests/exports/<commit>`), through that Part's entry in the week's driver (`drivers/w4.py`).
   - The driver plugs the fake server in, as your tests do. For `python -m aiofetch`, only the network under httpx is faked, so your settings, `make_client` and `HttpxTransport` all really run.
   - Only the driver's entry is recorded, as a hidden "you" frame. START is your first call, END its output.
3. The server rebuilds that week's map with `flowmap_tests/tools/build_project.py`, with your runs as a separate list. The page plays the new run.

**After a commit,** the hook's `flowmap_tests/tools/flowmap.py update` ends with `server.py --refresh`:

1. Your saved runs are played again (the same entry, the same input) on their Part's new code. One that can't run there any more stays on its old code, rebuilt from git when the tests map has deleted it.
2. The suggestions are made again for each Part whose commit changed.
3. The week's map is rebuilt.

A running server notices on the next page load: reload the page. If the hook was skipped, that page load does the work itself. A Run pressed on a page from before the commit asks you to reload first.

**Shared, not copied:** the recorder, the scanner and the page all come from `flowmap_tests`. Your runs only add a run menu, the input box and the lines your runs took; the map's cards are the same as on the tests map.

## Safety

- The same rules as recording tests:
  - no network beyond this machine;
  - `*_API_KEY` / `*_TOKEN` removed and every proxy pointed at a closed port;
  - at most 90 seconds per run.
- Your code runs in an empty throwaway folder, so it never reads your real `.env`. W4 gets a fake key, `playground-not-a-real-key`.
- Your input is passed to the driver as text, never run as code.
- The server listens on 127.0.0.1 only. It answers only requests made to its own name, and runs only for its own page (a secret made at each start). So a website you visit can't trigger a run.
- Each server keeps its own page and secret, so a second server (another port) never breaks the first one's page.

## Files

| Path | What it is |
|---|---|
| `server.py` | The local server: the page, the Run button, recording, keeping the last 20 runs per week; `--refresh` brings every week up to its newest commit |
| `harvest.py` | Runs a Part's tests once and notes what they pass into your code |
| `suggest.py` | Turns those values into each Part's Try: suggestions |
| `drivers/w1.py` … `w4.py` | How your input reaches each week's code: `PARTS`, per Part, its entries (label, hint, the function that runs it, its `from` rule) and its hand-written suggestions |
| `drivers/_input.py` | Reads `path=answers` words and `name=value` settings, writes them back from a test's values, and the call entry |
| `tests/` | `test_scenarios.py` (every hand-written suggestion of every Part, on that Part's code: each one runs, a good one doesn't raise, and together they reach every component; and every Part gets suggestions from its tests), `test_follow.py` (saved runs follow a commit, a page load after a commit, suggestions from tests, the call entry), `test_playground.py` (a server in a throwaway folder: Parts, two servers, the page in Chrome, every page guard), `run_in_page.mjs` (uses the real page) |
| `runs/`, `build/` | Your runs and the page: on your machine only, not in git and not synced |
| `PLAN.md` | The checklist this was built from |

Run the tests with `python3 -m unittest discover -s flowmap_playground/tests` (about five minutes; needs Chrome and node for the page tests).

## A new week

A new week only adds its driver, `drivers/w5.py`, written when the week is added to the map:

```python
def run_stream(text):              # your input -> the week's entry point, on its fake
    from stream_svc.app import ...   # your project's code: imported inside the entry, so the driver loads at any Part
    ...

STREAM = {"label": "stream", "hint": "/stream?n=3", "run": run_stream,
          "from": {"app.stream": lambda a, before: f"/stream?n={a['n']}"}}   # a test's values -> what you'd type

PARTS = {                          # every Part, with its own entries and 2-4 suggestions (a good one, a bad one)
    "1": {"entries": {"stream": STREAM}, "scenarios": [
        ("stream", "/stream?n=3", "good", "Three events stream in"),
        ("stream", "/stream?n=0", "bad", "Zero events: a 400"),
    ]},
}
with_call(PARTS, 'app.health()')   # every Part also gets "a function of yours" (from _input.py)
```

Then `tests/test_scenarios.py` must pass: every suggestion runs, each Part's suggestions together reach every component it has, and every Part gets suggestions from its tests. A Part left out of `PARTS` borrows the row before it; the first Part needs a row.

**A component nothing can reach yet** (starter code that a later Part starts using) is left out only with a reason in that Part's row: `"not yet": {"results": "starter code; run_all starts using it in Part 3"}` (W2 Parts 1–2). The test fails if the note goes stale: the component isn't in that Part, or a suggestion now reaches it.

## What could go wrong

| What you see | Why | What to do |
|---|---|---|
| The page says "too long to step through" | Over 5,000 events | A smaller input (fewer jobs, fewer paths) |
| "get_item takes item ids" | The input didn't fit the entry | Type what the box's hint shows |
| A new commit isn't in the playground | The page is from before it | Reload the page. Still missing: `python3 flowmap_tests/tools/flowmap.py update` (the hook may have been skipped) |
| "reload the page" after Run | A commit came in after the page loaded | Reload it |
| "Nothing to run at W3" | No row for that Part, nor for any Part before it | Add one, with its suggestions, and run `tests/test_scenarios.py` |
| The link doesn't open | The server isn't running, or another program has the port | `python3 flowmap_playground/server.py --port 8766` |
| The claude.ai map has no input box | That copy can't run Python | Use the local page |
