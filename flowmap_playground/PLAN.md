# flowmap_playground plan: type an input, watch it travel START → END

When a task is done, tick it and strike it through: `- [x] ~~the task~~`.

Plans 1–3 are the history of how the playground was built; a later plan can change an earlier one (Plan 2 made the box run the selected Part, not the newest). How it works now: [README.md](README.md) and [the handbook](../flowmap_tests/HANDBOOK.md).

Agreed with Hari on 2026-10-28 ("execute"). The shared code stays inside `flowmap_tests` (no `flowmap_core`).

## 1. Split the folder

- [x] ~~`git mv flowmap flowmap_tests`. Nothing inside it moves.~~
- [x] ~~Fix the old `flowmap/` path in `flowmap_tests/README.md`, `PLAN.md`, `tools/flowmap.py` (its messages), the memory note and the teaching note.~~
- [x] ~~`ai-eng-projects/sync.sh` copies from `flowmap_tests/`, and copies `flowmap_playground/`'s code (not its `runs/` or `build/`). Its `.gitignore` follows the new names.~~
- [x] ~~The tests map is unchanged: `build --check` says ok (the saved map in `build/expected.json` matches) and every tool test passes.~~
- [x] ~~List the other files that still mention the old `flowmap/` path.~~

## 2. Shared code (each change invisible to the tests map)

- [x] ~~`trace.py`: a second mode that runs a playground driver instead of a pytest test. Your input enters through a hidden "you" frame, like a test's, so START is your call. What the code printed is kept. The test mode is untouched.~~
- [x] ~~`build_project.py`: an optional "your runs" folder, saved as a separate `play` list. Without it the output is byte-identical.~~
- [x] ~~`page/flowmap.html`, only when the data has playground runs: the input box (week, entry, text, Run), your runs in the run menu (`/v2/items/7 · 31 steps · ↩ 0`), and END with the printed rows plus the exit code.~~

## 3. The playground (`flowmap_playground/`)

- [x] ~~`drivers/w1.py`: `cli.main(args)`, with your log lines on stdin (`-`).~~
- [x] ~~`drivers/w2.py`: `cli.main(args)`; it starts its own local server.~~
- [x] ~~`drivers/w3.py`: `client.fetch_many(paths)` on ChaosAPI (`/items/3=404` scripts an answer).~~
- [x] ~~`drivers/w4.py`: `main(paths)` and `client.get_item(ids)` on FlakyAPI (`/items/1=503,503,200` scripts answers).~~
- [x] ~~`server.py`: only on 127.0.0.1, only for its own page (a secret per start). Run → record on the newest Part's code → play. Keeps the last 20 runs per week.~~
- [x] ~~`tests/`: one example input per driver, and the server answering a run.~~
- [x] ~~`README.md`.~~

## 4. Finish

Found and fixed on the way (each with a test first): pytest's cached test files kept the old `flowmap/` folder, so a moved project lost its test frames; `@lru_cache` functions weren't recorded; a coroutine of yours run by `asyncio.run` had no START/END; a folder path ending in `/` and the `<string>` call site of a dataclass `__init__` leaked a local path; a brand-new playground entry's first run had no END; the new W4 column was called `  main  `.


- [x] ~~W4 by hand in the real page: `/v2/items/7`, `get_item 1500` (ItemMissing), `get_item 3007` (the moved detour), `/items/1=503,503,200` (retries).~~
- [x] ~~The tests map is still unchanged (`build --check` ok, tool tests pass).~~
- [x] ~~Hari re-runs `python3 flowmap_tests/tools/flowmap.py hook W2` and `hook W4`: the old hooks point at `flowmap/`.~~ Done (2026-10-28). `hook` used to keep a stale post-commit ("already installed"); it now rewrites old flowmap lines (`tests/test_hooks.py`).

# Plan 2: run on the selected Part, with suggested inputs (agreed 2026-10-28, "execute")

- [x] ~~**Hook check:** a test for exactly the reported case (`hook WX` on a post-commit holding the old template and the old `flowmap/` path). It fails on the code before 42d702d and passes now (`flowmap_tests/tests/test_hooks.py`).~~
- [x] ~~**One table per driver:**~~ `PARTS` lists each Part's entries and 2–4 scenarios (good, bad, up to two more), each with a one-line description. Drivers import your project's code inside each entry.
- [x] ~~**W1:**~~ 1 `parse_line` · 2 `ParserConfig` + `parse_line` · 3 the filters · 4 `pipeline.run` · 5 the command on a file (and on stdin as a second entry).
- [x] ~~**W2:**~~ each Part's own function on MockServer (`run_serial`, `run_gather`, `run_all`/`run_with_progress`, `Fetcher.stream`, `run_group` + the command); `--help` reaches `cli` in Parts 1–4.
- [x] ~~**W3:**~~ 1 `get_json` · 2 `retry_call` · 3 `fetch_many` · 4 plus the limiter · 5 plus embeddings.
- [x] ~~**W4:**~~ "W3" = W3 Part 5 · 1 the same · 2 `fetch_many` through the seam · 3 plus `get_item` · 4 plus `jsonl` · 5 plus `python -m aiofetch`.
- [x] ~~**Server:**~~ reads the tables, records on the selected Part's export through that Part's entry, keeps each run under its Part. Each server serves its own page (from memory, its own secret), so a second server can't break the first.
- [x] ~~**Page:**~~ the box follows the Part pill; a "Try:" dropdown fills the box (you press Run); "Nothing to run at Part X" when there's no entry.
- [x] ~~**Proof:**~~ `tests/test_scenarios.py` records every scenario of every Part on that Part's code; fails if one doesn't run, a good one raises, or a component present at that Part is never reached. Server tests: Part chosen, nothing-to-run, two servers at once. W2 Parts 1–2 can't reach `results` (starter code nothing calls before Part 3): Hari chose a `"not yet"` note with its reason, which the test keeps true.
- [x] ~~**Docs:**~~ the playground README and the handbook (a new week adds only its driver's table).
- [x] ~~**Unchanged:**~~ the tests map (`build --check` ok), tool tests and playground tests pass; checked by hand on port 8798 (never 8765).

# Plan 3: the playground follows every commit, with suggestions from your tests (agreed 2026-10-30, "execute")

The crash of 2026-10-29: after `chore: release v0.2.0` joined W4 Part 5, the tests map's update deleted `exports/f952126`; the 10 W4 runs saved on it stopped the server from starting.

- [x] ~~**Tests first:** a saved run whose code copy was deleted still builds (it failed with exactly that error); one whose commit is gone from git is dropped with a note; after a commit a saved run is played again on the new code; one that no longer runs stays on its old code; a page load with no commit rebuilds nothing; after a commit a Run asks for a reload and the reload rebuilds (`tests/test_follow.py`).~~
- [x] ~~**Crash fix:** `build` makes a run's code copy again from git; drops a run only when its commit is gone.~~
- [x] ~~**Saved runs follow their Part:** `follow` plays them again (the same entry and input) on the Part's new commit.~~
- [x] ~~**Page load:** each week's signature (its Parts' commits, the tests map's build, the drivers, this code); a changed one is refreshed before the page is served. A stale page's Run gets 409 "reload the page".~~
- [x] ~~**Suggestions from tests:** `harvest.py` (each Part's tests once, the values your functions got), each entry's `from` rule, the call entry for a new function with plain values, `suggest.py` (new tests first; one fine, one raising; played before shown; up to 4). Kept per commit in `build/`. The drivers' own suggestions are the fallback.~~
- [x] ~~**A new Part without a row** borrows the row before it; its suggestions come from its own tests.~~
- [x] ~~**One commit updates both:** `flowmap.py update` ends with `server.py --refresh` (`tests/test_hooks.py`: it runs after the map, and runs the playground next to `flowmap_tests`).~~
- [x] ~~**`init` installs the hook** (before the first build), so a new week is one command (`tests/test_hooks.py`).~~
- [x] ~~**Proof:** `tests/test_scenarios.py` also checks that every Part of every week gets suggestions from its tests (or a `"no suggestions"` note with its reason, which must stay true; none needed today).~~
- [x] ~~**Unchanged:** the tests map (`build --check` ok); tool tests and playground tests pass; checked by hand on port 8798 (Try: on W4 Parts 3 and 5, the call entry on Part 4), never 8765. Your runs were backed up to `~/history-backups/2026-10-30/playground-runs` before their first refresh.~~
- [x] ~~**A new week without a driver** (W5 today) is in the playground anyway: `drivers/_auto.py` gives every Part "a function of yours"; a running server shows a new week on the next page load (`tests/test_follow.py`, NewWeek).~~
- [x] ~~**The handbook:** a new repo goes on `sync.sh`'s list; the sync publishes your project's code with its history; `update.log` shows both maps following a commit; a new week needs no restart.~~

# Plan 4: Shrink, Clear, and any function with its setup built (executed 2026-10-30)

The report of 2026-10-30: `lab.main()` (W5) said "too long to step through (5645 events)". It takes no input, so nothing could be made smaller. The fix must work for every week, Part, function and size, past and future, not just `lab.main`.

**Measured before starting** (my runs, 2026-10-30):

| What | Time |
|---|---|
| `lab.main()` untraced / recorded | 11.0 s / 12.3 s, 5,663 steps (`load.<one>` ×400; 10 s is `/slow_blocking` sleeping 200 × 0.05 s) |
| A 4-step Run (W4 `storage.is_json_object`) | 0.95 s, of which ~0.7 s is Python compiling libraries from scratch (the recorder's fresh `flowmap-pyc-` folder each run) and 0.33 s is importing pytest (overlapping) |
| Python + the project's imports alone | 0.15 s (aiofetch), 0.27 s (stream-svc) |
| W4 map build after a Run | 0.72 s, half of it 136 separate `git show` calls |
| Tests-map rebuild in the hook | 29 s (from `update.log`; not profiled yet) |

Python 3.14 in every project; changing a call's values as it starts (`frame.f_locals`) works there (checked).

## 1. Tests first, and a baseline

- [x] Back up `runs/` (as in Plan 3) and fingerprint every project's files and every `flowmap_tests/exports/` copy. Any change to them by the playground is a failing test.
- [x] Failing tests for: `lab.main()` too long with nothing to shrink; a method (`client.AiofetchClient.get_item(1500)`) can't run today; the moved-folder bug the fresh bytecode folder was added for.

## 2. Speed (each change kept only if a timing shows it faster and every test still passes)

- [x] **A lasting bytecode cache** (`flowmap_tests/build/pyc/`, by each file's full path) in `tools/trace.py` and `harvest.py`, instead of a fresh folder per run. A renamed folder still can't reuse old files.
- [x] **No pytest import** in a playground Run (it never runs a test there).
- [x] **The map build reads each commit once:** one `git cat-file --batch` instead of 136 `git show` calls; the scan saved per commit; each function's code walked once (`tools/build_project.py`). `build --check` must still say ok: the tests map stays identical.
- [x] **Profile the hook's 29 s** tests-map rebuild, then fix what the profile shows.

## 3. The index (new `index.py`): read once per commit, kept in memory while the server runs

Not saved to `build/index/`: reading it takes 5 ms (W5 Part 1) to 41 ms (W4 Part 5), measured, so a file would not be faster.

- [x] **Call graph:** `calls[fn]` and `callers[fn]` (sets), each line with its call site (file, line, argument text); from the scanner's own call resolution (no second copy) plus calls the harvest saw at runtime. Static calls only: the runtime calls come in through step 1 (the test runs).
- [x] **Multi-source BFS** from every runnable start (tests, `main()`s, driver entries, functions with plain values): `parent[fn]`, the hop before it on the shortest path. Starts are your functions that need nothing (`main()`s among them); tests are step 1.
- [x] **Builders (an AND–OR graph), solved by forward chaining:** `builders[type]` (a function of yours returning it, its constructor, a `conftest.py` fixture, a fake, values a test built it with); a counter of missing pieces per builder; the queue order gives each type its shortest chain. No `conftest.py` fixture is called directly: a test that uses it is step 1. Enums are made from their first member.
- [x] **Fakes that fit an interface:** `methods[class]` sets, a reverse index, set intersection.
- [x] **Where each name gets its value** (per function): parameter defaults, assignments, module constants. Shrink follows it backwards (backward slicing), across callers through the call sites.

## 4. Shrink

- [x] **The panel** under the input box: each value that decides how long the selected entry runs (`load · requests  200 → [20]  your test uses 20 · ≈ 570 steps, estimated`). Suggestions: the value your tests pass, else 3 (a number) or the first 2 items (a list). Edit any box; Run uses what's in them.
- [x] **Too long:** the panel opens with the values that made it long (the most repeated call, traced back to its loop's count).
- [x] **Typed in:** `lab.main(requests=5)`: a name the function doesn't take goes to the function below it that does. Two take it: both are listed, you pick. Two take it: the message names both (`… give it to one of them, e.g. X.name`).
- [x] **A size from outside the code** (your `--jobs 300`, a file): the page names that input instead of changing code.
- [x] **Applied in memory only:** inside the run's own process, just before Python compiles that one module; same file name and line numbers, so the map lines up. Never written to your project or `exports/`, and a changed module never goes into the bytecode cache.
- [x] **The card shows it:** `requests = 20 (yours · the code says 200)`.

## 5. Clear

- [x] **Kept per week** in `runs/<week>/changes.json` (Shrink values and your picks from step 4 below), by function and name, not line number, so they follow your commits. A change whose function or name is gone is dropped with a note. Changed while building: a kept change this Part's code doesn't have is named in a note and not used, but kept (another Part may have it) until Clear.
- [x] **A saved run keeps the changes it was made with,** so `follow` plays it again the same way after a commit.
- [x] **Clear** drops that week's changes; the next Run uses the code's own values.

## 6. Any function, with its setup built

- [x] **The call entry takes methods and functions that need objects** (`client.AiofetchClient.get_item(1500)`), still only with plain values typed.
- [x] **Its setup, tried in order:** 1. a test that reaches it (your values swapped in as the call starts); 2. your code that calls it (the BFS path; swapped in at the target); 3. built from type hints (the builders); 4. the page asks for just the missing piece, listing what it found, and remembers it until Clear.
- [x] **START is that call, END its result;** the page says which way the setup was made (`set up by test_get_item_…` / `built: get_settings() → from_settings(…)`).
- [x] **Real outside services** (Postgres, a real API) aren't built: your fakes stand in, or "needs Postgres running". Not built: a parameter of an outside type is asked for (step 4), like any piece nothing makes.

## 7. Proof (I run all of it myself; the report shows each result)

- [x] **Every Part of W1–W5:** every value Shrink finds runs under 5,000 steps with its suggestion; every public function is tried through steps 1→4, with a count per step and the ones that ask you.
- [x] **Throwaway sample projects** (`tests/`) for what your weeks don't have yet: no test, no caller, no type hint, a Protocol parameter, async, a context manager, a classmethod builder, two classes needing each other, a missing outside service.
- [x] **Clear and changes:** kept between runs and across a server restart; follow a commit; dropped with a note when gone; Clear restores the code's values.
- [x] **The page in Chrome** (port 8798 only, never 8765): the Shrink panel, Clear, the "pick one" question, a stale page after a commit. Servers in the tests use a free port of their own, never 8765.
- [x] **Fingerprints** of projects and `exports/` unchanged after everything.
- [x] **Timings:** each step before and after, and each algorithm's time on every week. Measured, never estimated.
- [x] **Nothing else broke:** the tests map (`build --check` ok), every tool test, every playground test, the page checks on every Part and run.

## 8. Docs and report

- [x] README (Shrink, Clear, any function and its 4 setup steps, the limits, "What could go wrong"), the handbook, the `flowmap_tests` README for the bytecode cache.
- [x] **The final report:** every scenario run, pass/fail, what broke and how it was fixed, before/after times.

**Measured after** (2026-10-30, `tests/bench.py`, the fastest of 3):

| What | Before | After |
|---|---|---|
| A 4-step Run (W4 `storage.is_json_object`) | 0.98 s | 0.42 s |
| W4 `get_item 1500` | 0.99 s | 0.41 s |
| Run pressed (record + map + page) | 1.89 s | 0.72 s |
| W4 map build after a Run | 0.76 s | 0.17 s |
| Tests-map rebuild in the hook | 29 s | 1.6 s with nothing new; a W5 commit 3.2 s, a W4 commit 11.9 s (Chrome checks only the changed week) |
| `lab.main()` | refused, 5,663 steps | Shrink: `lab.load · requests 200 → 20`, 605 steps |

## Limits (stated, not built)

- Changes **values** (numbers, defaults, constants, lists), never **logic**: a wrong kind of input shows your code's real error.
- A value worked out at runtime from outside data can't be traced back; the page says which input to change.
- Built objects start fresh (a new client, an empty cache).
- No Rust or C++: measured, the slow parts are your code's own work and Python setup costs, which a faster language can't remove. What a faster language could still win is measured after section 2, not guessed.
