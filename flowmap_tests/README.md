# flowmap_tests

**Start with [HANDBOOK.md](HANDBOOK.md):** what to do each week, how both maps stay up to date, and every rule.

An animated map of how data moves through each week's project: from what you call (START) to what your call returns (END). A call travels a line as a signal, the values sit in the cards, and an answer rides back. It grows Part by Part as you commit.

The runs are recorded by running the project's tests, because a test is a ready-made caller. But the map shows only your code (`src/`). The test code (`tests/`) stays hidden, except, from Week 5, the bits of it your code calls in the middle of a run (see [What the page shows](#what-the-page-shows)).

Open `build/flowmap.html` in a browser. Refresh it after a rebuild. To type your own input and watch it run instead, see [`../flowmap_playground/`](../flowmap_playground/README.md). It uses this folder's recorder, scanner and page. For what you must do so every Part and every week shows up, see [How the map stays up to date](#how-the-map-stays-up-to-date).

## Projects on the map

| Week | Project | Repo | Parts | Updates by itself |
|---|---|---|---|---|
| W1 | logparse | `projects/logparse` | 1–5, set by hand in `cfg/w1.py` (its commits don't name their Part) | No hook: the week is finished |
| W2 | async-batch-fetcher | `projects/async-batch-fetcher` | 1–5, from its `Week 2 Part N` commits | Yes (hook) |
| W3 | aiofetch | `projects/aiofetch` | 1–5, from `Week 3 Part N` commits | Yes (hook) |
| W4 | aiofetch | `projects/aiofetch` (same repo as W3) | W3 (where Week 3 ended), then 1–5 | Yes (the same hook) |
| W5 | stream-svc | `projects/stream-svc` | From its `feat(w5pN)` commits (in progress) | Yes (hook) |

Pick the week in the project menu (top left), then a Part in the top bar.

## Learning with the map

1. **Pick a Part and look at step 0:** what this Part adds glows white, and dashed means changed. That's the Part's story before anything runs.
2. **Read START:** it is what you call, e.g. `client.fetch_many(6 urls)`. END, once the run finishes, is what that call returned.
3. **Step with ▶| and watch the details box:**
   - each step is one hand-off: FROM which function, IN which values, OUT what came back, BACK TO whom;
   - the line under BACK TO shows where the value lands in the caller's code.
4. **Compare a good run with an error run:**
   - a good run goes straight through every layer;
   - an error run lights up the error cards in red (`error_for`, `TransientError`) and shows a retry looping, or a raise reaching END.
5. **Step back with ◀** whenever a step goes by too fast. The map returns exactly to how it was.
6. **Press Grow** to watch the whole project come together, Part by Part.
7. **Make it readable:** Close-up (the magnifier) for bigger cards, and A− / A+ for the box text.


## What the page shows

- **Columns, left to right:** START, then one column per component (fan-out, rate limiter, breaker, retry, transport…), then END.
  - Each column header has the component's question ("may I spend budget?") and its live state ("CLOSED · fails 0").
  - Each card underneath is one function, with its file and its latest value. `→ '/items/1'` is what went in; `↩ {id, name}` is what came back.
- **Parts (top bar):** each Part shows only the code that existed at that commit.
  - At step 0, what the Part added is outlined in white. A dashed outline means changed.
  - Once the run moves, only a small corner square stays on those cards.
- **A run (bottom bar):** ▶ plays, and ◀ / ▶| step. Every step shows one hand-off on the map. Stepping back undoes it exactly.
  - **→ / ←** step too, wherever you last clicked (a menu, the slider, a button). Only while you type in a text box do they move the cursor instead.
  - Quiet events ride along with the step before them: a field changing, a wait, the test's own frames.
- **Your code only:** everything from `src/` plays in the order it happened. For example, in W3:
  1. building the fake server (`chaos = ChaosAPI(script={"/items/3": [404]})`);
  2. building your client (`client = AiofetchClient("http://api.test", …)`) and opening it (`async with client`);
  3. your call (`client.fetch_many(6 urls)`) and everything it sets moving;
  4. closing the client;
  5. END: the output, just what your call returned, e.g. `↩ [6 Result]`.
- **Test code is hidden:**
  - the test's own functions and helpers;
  - the checks on its `assert` lines: building the expected value, `==` / `<` / `in` / `len`, and yes/no reads like `r.ok`. The call being tested stays, even on an `assert` line (`assert ok.to_row() == {...}`);
  - Weeks 1–4: small functions the test hands in (like `call()` or a filter `lambda`) are skipped over. In W3 Part 2, `retry_call` → `get_json` is drawn directly.
- **From Week 5, test code in the middle shows:** a stand-in your code calls, a function the test hands in, a monkeypatched function. They get their own column, **from the test**, just before END. START is still your first call, and END its output.
- **Names:**
  - an object shows with the name your code gives it (`client.get_json`, `breaker.call`, `limiter.acquire`), or its class in snake_case if the code names it nowhere (`flaky_api`);
  - "you" appears only where you act: the START card ("you call"), the caption before the run starts, and FROM / BACK TO in the box of a call you made.
- **Details box (right):** for the running call it shows FROM → IN → function → OUT → BACK TO, plus the caller's line with the value filled in. **A− / A+** change its text size. **Follow** keeps it on the running call.
  - **Resize it:** drag its left edge (width), bottom edge (height) or the corner between them. The ⤢ button next to × (or a double-click on an edge) puts it back to the original size. The size is remembered in this browser; the text size keeps its own buttons.
- **Who's waiting (left rail):** the call stack, one tab per parallel task.
- **Colours ("Ice" palette on black):**
  - your code's calls and waiting lines: ice blue;
  - answers: mint;
  - errors: red;
  - parallel tasks (T1, T2, …) and threads (TH1, …): white, orange, lime and pale yellow, in turn;
  - everything at rest: grey.
- **Zoom controls:** **Close-up** (the magnifier) shows bigger cards and makes the camera follow the run. Fit (the corners) shows the whole map.

## Using it

| Command (run from anywhere) | What it does |
|---|---|
| `python3 flowmap_tests/src/flowmap_tests/flowmap.py build` | Rebuild everything: export each Part's code, record runs where needed, build the page |
| `python3 flowmap_tests/src/flowmap_tests/flowmap.py build --check` | Same, then check every Part and run in a browser, compare with the saved map, and run the tool tests if the tools changed (see [Checks](#checks)) |
| `python3 flowmap_tests/src/flowmap_tests/flowmap.py build --accept` | Same as `--check`, then save this map as the expected one: for when an old week changed on purpose |
| `python3 flowmap_tests/src/flowmap_tests/flowmap.py hook W4` | Repair the git hooks in that project's repo (after each commit and after each `git pull`). `init` installs them; this rewrites one that points at an old folder |
| `python3 flowmap_tests/src/flowmap_tests/flowmap.py update` | What the hook runs in the background after each commit: build and check, quietly, then bring the playground up to the same commit (`flowmap_playground/src/flowmap_playground/server.py --refresh`) |
| `python3 flowmap_tests/src/flowmap_tests/flowmap.py note` | The one line the hook prints after a commit |
| `python3 flowmap_tests/src/flowmap_tests/flowmap.py init W5 projects/x --week 5 --practical w05_plan.md` | Start a map for a new project, and install its git hooks (`--week PF1` for the production bridge) |
| `python3 -m unittest discover -s flowmap_tests/tests` | The tool tests by hand (a rebuild runs them whenever the tools change) |

## How the map stays up to date

### What you must do

| When | You do | Why |
|---|---|---|
| **Once per week's project** | Run `init` for the week yourself (see the table below). It also installs the git hooks, and Claude isn't allowed to install them | The map only knows the weeks that have a settings file in `cfg/`. The hooks rebuild the map (and the playground) after each commit and each `git pull` |
| **Every commit** | Name the Part in the message: `feat(w5p1): what it adds`. Any type works (`fix(w5p1)`, `test(w5p1)`, `docs(w5p1)`); a Stage is `(w16s2)`, the production bridge `(pf1p2)`. The old `Week 5 Part 1: …` still works | The Part is found from this message. A commit that names no Part joins the Part before it |
| **Every Part** | Add tests for what the Part builds, anywhere under `tests/` (`tests/unit/test_x.py` too). Fixtures, `async def` tests and parametrize all work | The tests a Part adds become its runs on the map |
| **When a Part is finished** | Merge it into `main`. When it is merged on GitHub (from Week 7), `git pull` it | The newest Part counts as *in progress* (a dashed pill) until `main` contains it. The pull hook updates the map |
| **To see the change** | Refresh `flowmap_tests/build/flowmap.html` in your browser | The page doesn't reload itself |
| **To share it** | Ask Claude to republish the claude.ai link | That link is a copy and doesn't update by itself |

### What happens by itself after each commit

1. **The note:** the hook prints one line straight away, for example:

   ```
   flowmap: W4 Part 4 added · Typed results · updating build/flowmap.html in the background · last check: ok
   ```

2. **The rebuild:** in the background (usually under a minute), the map:
   - finds the Part from the commit message;
   - copies that commit's code into `exports/` (your working tree is not touched);
   - records the tests the Part added on that code and keeps the best two;
   - rebuilds every project's map;
   - runs the [checks](#checks);
   - brings the playground up to the same commit: your saved runs play again on the new code, and each Part's Try: suggestions are made again from its tests (see [`../flowmap_playground/`](../flowmap_playground/README.md)).

   The log goes to `build/update.log`, and the check result to `build/check.txt`.
3. **On the map:** refresh the page and the new Part has its own pill. At step 0 its new pieces glow white (dashed means changed), and its runs play.
4. **Problems:** the next commit's note says how the last check went: `last check: ok`, or `last check: 2 problems (see flowmap_tests/build/check.txt)`.

| Kind of commit | What the map does |
|---|---|
| `feat(w5p2): …` (a new Part number) | A new Part: "W5 Part 2 added" |
| Another commit for the same Part (`fix(w5p2): …`, or `Week 4 Part 4 redo: …`) | The same Part, with its code moved to the newest commit: "W5 Part 2 updated" |
| A commit whose message names no Part | Joins the Part before it |
| A `git pull` that brings a Part merged on GitHub | The same as a commit: the pull hook updates the map |
| A commit while a rebuild is still running | It gets one more rebuild when the first one ends |
| A Part whose new tests barely touch your code (fewer than 3 of your functions) | The Part is on the map without a run; `build/check.txt` says why in a `note:` line |
| A function that is still a starter stub (`raise NotImplementedError`, with or without a `# TODO`) | Not on the map until the Part that fills it in. An abstract method (`@abstractmethod`, or on an `ABC` or `Protocol`) stays |

### Every week's project

Each new week takes one command, done once. After that, every commit updates the map (and the playground) as above.

| Where the week's code lives | Run once (from `ai_eng_workspace/`) | After that |
|---|---|---|
| The same repo as an earlier week (W4 carried on in `aiofetch`) | `python3 flowmap_tests/src/flowmap_tests/flowmap.py init W5 projects/aiofetch --week 5 --practical w05_plan.md` | That repo's hook is already installed, so every commit updates the map |
| A new repo | The same `init`: it installs that repo's hooks too | The same |
| Several repos in one week (W18 builds `llm-client-kit` and changes `aiofetch`) | One `init` per repo, each with its own key: `init W18-llm projects/llm-client-kit --week 18` and `init W18-aiofetch projects/aiofetch --week 18` | Each is its own entry in the project menu (`W18 · aiofetch`). A W18 commit in `aiofetch` never changes W3 or W4 |

- **What `init` works out:** the Parts come from your commits, and their titles from the `--practical` plan's `Part N - …` or `Stage N - …` headings (or the commit messages without one). Columns, runs, START and END are worked out too, and the week is checked. It then appears in the project menu.
- **Hooks installed:** `aiofetch` (W3, W4), `async-batch-fetcher` (W2) and `stream-svc` (W5), each with both hooks (after a commit and after a `git pull`). `logparse` (W1) is finished and has none. Each new week's `init` adds its repo.

### What does not update by itself

- **The claude.ai link:** ask Claude to republish it.
- **A new week before `init` has run for it:** its commits don't show on the map. A hooked repo doesn't create a new week's settings by itself.
- **A repo without a hook:** run `python3 flowmap_tests/src/flowmap_tests/flowmap.py build --check` after committing, or install the hook.
- **The check on a machine without `google-chrome`:** the map still rebuilds, but nothing is checked.

## Adding a project

`init` works when the project looks like this:

- **Commit names:** each commit names its Part, `feat(w5p1): what it adds` (or the older `Week 5 Part 1: what it adds`). A commit without a Part joins the Part before it.
  - The newest Part counts as *in progress* until `main` contains it.
- **Code layout:** the code is in `src/<package>/` with an `__init__.py`. Subpackages are fine: `adapters.alpha` is named by its path, and each top-level subpackage is one column (`adapters/`).
  - Python outside `src/` that is yours too (`scripts/`, `examples/`) comes in with one line in the cfg: `CODE_DIRS = ["scripts"]`.
- **Tests:** anywhere under `tests/`, as pytest runs them: fixtures, `async def`, parametrize (its first case), and tests in a `class Test…`.
- **Python:** the project has its own `.venv` with Python 3.12 or newer and pytest. The recorder uses `sys.monitoring`; the current projects run 3.14.

If the commits are not named that way (like Week 1's `logparse`), write `cfg/<key>.py` by hand and list the Parts yourself. Paths are relative to the workspace. See `cfg/w1.py`:

```python
KEY, NAME, WEEK = "W1", "logparse", "W1"
REPO = "projects/logparse"
PARTS = [("751fd5a", "1", "A typed log record"), ...]   # (commit, label, title)
COMMIT, BRANCH = "d66d1e1", "main"
```

Everything else is worked out:
- columns (one per module, in the order a call reaches them);
- summaries (each docstring's first line);
- runs (the tests each Part added);
- START and END.

To shape a map by hand, add a `MAP` (columns, their questions, and edges), `RUN_META` (hand-picked runs), `EXTRA_DESC` (summaries) and `FAKES` (test fakes whose name doesn't say so, like `chaos.ChaosAPI`). See `cfg/w3.py`.

## How it is built

`src/flowmap_tests/flowmap.py build` runs these steps for every `cfg/*.py`:

1. **Parts:** `src/flowmap_tests/gitparts.py` reads the git history into Parts. Each Part's code is its last commit, or the cfg's `PARTS` when it has them.
2. **Exports:** each Part's commit is copied read-only into `exports/<commit>/` with `git archive`. Your working tree is never touched. The files `build_project.py` scans are read straight from git (one `git cat-file --batch` for the whole history).
3. **Conditions:** `src/flowmap_tests/conds.py` scans the last export for the condition each call runs under (`if…`, `on error`, `in loop`).
4. **Runs:** for each Part without hand-picked runs, `src/flowmap_tests/pickruns.py`:
   - takes the tests that Part added;
   - records them on that Part's code with `src/flowmap_tests/trace.py`, using the project's own Python. pytest runs the test, and only its body is recorded (fixture setup isn't);
   - keeps the two that pass through the most project functions, from different test files, preferring the shorter run. A run over 5,000 events is too long to step through and is skipped.

   Results are cached in `runs/auto/` until the Part's commit changes. When the recorder itself changes (`RECORDER` in `pickruns.py`), the same tests are recorded again, so a Part's stories don't change under you.
5. **Map data:** `src/flowmap_tests/build_project.py` scans every Part's code (`src/flowmap_tests/scan.py`: functions, classes, calls, imports, docstrings) and works out the columns, lines, what is new or changed per Part, test fakes and assert-only checks. Starter stubs don't count as built. It writes `build/proj_<key>.json`. A commit's scan is kept in `build/scan/` (a commit never changes), so only new commits are scanned. The playground's `index.py` uses the same scanner.
6. **The page:** `src/flowmap_tests/combine.py` joins the projects into `build/data_all.js`. `src/flowmap_tests/inject.py` puts it into `page/flowmap.html`, which gives `build/flowmap.html`.
7. **Check (`--check` and the hook):** see [Checks](#checks). Chrome checks only the weeks whose map data changed; the others' results are kept in `build/check_cache.json`, and every week is checked again when the page or the checks change.

**Compiled files** of your code and of the libraries are kept in `build/pyc/`, by each file's full path, so each one is compiled once, not at every run.

When the page loads a run, it keeps only your code and drops the test code (`flowOnly` in the page), then groups the events into steps you can see (`STEPS`).

The playground shares these steps: `trace.py` also records a playground driver's entry (`play:` instead of a test), `build_project.py` takes an optional folder of your runs (saved as a separate `play` list), and the page shows its input box only when the data has playground runs. Without them, every output here is exactly the same.

| Path | What it is |
|---|---|
| `page/flowmap.html` | The page source: one file, HTML + CSS + JS (d3) |
| `pyproject.toml`, `uv.lock`, `.python-version` | A uv project on Python 3.14 with no packages: the tools run with `python3` by their path, from the hooks too |
| `src/flowmap_tests/` | The steps above; `flowmap.py` is the only one you run |
| `cfg/` | One settings file per project |
| `runs/` | Recorded runs (`runs/auto/` is made by the run picker) |
| `checks/` | Browser checks: `smoke.js` (every rebuild), plus real-mouse and real-keyboard checks `clicks.mjs`, `follow.mjs`, `stack.mjs`, `resize.mjs` (resizing the details box), `keys.mjs` (→ / ← step from anywhere) (by hand: `node flowmap_tests/checks/clicks.mjs file:///…/build/flowmap.html#W4`) |
| `tests/` | The tool tests, and `tests/sample/`: a tiny project with one example of everything the recorder must handle (`tests/sample_driver.py` is its playground driver) |
| `exports/` | Read-only copies of each Part's code (not in git, made again on build) |
| `build/` | The built page, data, logs and check result; `scan/` (each commit's scan), `pyc/` (compiled files) and `check_cache.json` (each week's last check). Not in git: delete it any time, it's made again |

## Checks

`build --check` (and the hook, after every commit and pull) checks the real map. Everything it finds goes to `build/check.txt`, and the next commit's note says `last check: ok` or `last check: 2 problems`.

- **Every run:** START is a call of yours, and END shows an output.
- **Every run:** it shows at least half of the functions of yours it really ran. This catches the "Part 4 has only 5 steps" kind of bug.
- **Every run:** every step shows something, and a step looks the same reached forward, backward or by jumping.
- **Every Part:** no words on top of each other, no line through a card, no card under a panel.
- **Every page:** no local paths (`/home/…`, `/tmp/…`), no numbered objects (`ReadStats#1`) and no "your code" text.
- **Every Part:** it has a run, or a `note:` saying why not.
- **Old weeks don't change by themselves:** each Part's summary (cards, lines, each run's START, END, steps and calls) is saved in `build/expected.json`. A Part whose commit is the same but whose map changed is a problem: a tool change did it. If you meant it, run `build --accept`.
- **The tool tests** (`tests/`) run whenever the tools, the page or the checks changed since they last passed. One of them builds a whole sample week (Week 4 and Week 5 Parts in `feat(w5p1)` commits) through the real pipeline.

### When you find a bug

1. First write a test in `flowmap_tests/tests/` that fails because of it (add to `tests/sample/` if it needs new code to record).
2. Then fix it.
3. Then `build --check` must say `ok`, and the tool tests must pass.

## What could go wrong

| What you might see | Why | What to do |
|---|---|---|
| A project has no Parts, or `init` fails | No commit names a Part (`feat(w5p1): …`, or the older `Week N Part X: …`) | Commit with the Part in the message; for old commits, list the Parts by hand in its cfg (`PARTS`, `COMMIT`, `BRANCH`), like `cfg/w1.py` |
| A Part has no run | `build/check.txt` says why: its new tests touch fewer than 3 of your functions, failed, were skipped, or are over 5,000 events | Add a test that goes through more of the Part's code, or record one by hand and list it in `RUN_META` |
| `check.txt`: "W2 Part 3 changed by itself" | An old week's map changed although its code didn't, so a tool change did it | If you meant it, `build --accept`. If not, it's a bug: ask for a fix |
| A check from the test shows up in a run | The test's assert spans several lines or uses `self.assertEqual`, so its calls aren't seen as being on an `assert` line | Assert on one line with `assert` |
| Strange columns | Without a `MAP`, columns are one per module in call order, a guess | Write a `MAP` in the cfg |
| A fake isn't with the fakes, or a card is missing | "Fake" means a class named `Mock…`/`Fake…`/`Stub…`/`Dummy…`, or listed in the cfg's `FAKES`; "assert-only" means it is only used on assert lines to judge a result. Both are guesses from the code | Add the class to `FAKES`. The page keeps any card a run really calls |
| A function appears only in a later Part | A starter stub (`raise NotImplementedError`) counts as not built yet, so it joins the map in the Part that fills it in | Nothing: that is the Part that built it. Make it `@abstractmethod` if it is meant to stay empty |
| Cards with no summary | The function has no docstring | Add a docstring, or `EXTRA_DESC` in the cfg |
| "NOT ON MAP" in the check output | Generator expressions and library internals have no card | Nothing: they play as quiet events |
| The claude.ai link shows an old map | It is a copy | Ask Claude to republish `build/flowmap.html` |
| The hook's check says "problems" | A check failed (see [Checks](#checks)) | Look at `build/check.txt`, then ask for a fix |
| No check runs | `google-chrome` is missing | Install Chrome, or skip `--check` |
| A commit prints "can't open file …/tools/flowmap.py" | The hook still points at an old folder (`flowmap/tools/` or `flowmap_tests/tools/`; the code is in `src/` now) | Run `hook` again: it replaces the old lines and keeps any others in the hook |
| A test tries the real network or a paid API | While recording, every connection that isn't to this machine is refused, `*_API_KEY` / `*_TOKEN` are removed and every proxy points at a closed port. Such a test fails rather than spend money. Local Postgres or Ollama still work | Keep tests on fakes |
| Real data in `runs/` | Recordings hold the real values your tests use | Don't record tests that read secrets or private files |
| Map too small to read | Docked panels take room on narrow screens | Close-up button, close the details box, or A− / A+ for the box text |
| A long run is slow to play | Some runs have hundreds of steps (W3 Part 5's outage run is the longest) | Use the slider, the speed menu (up to 1.25×), or the chapter ticks above the slider |

When asking for a fix, send a screenshot plus the project, Part, run and step number, for example "W4 Part 3, run 1, step 14: the box cuts off a value".
