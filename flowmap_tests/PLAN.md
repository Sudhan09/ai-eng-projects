# flowmap plan: fixes, future weeks (W5–W21) and safety net

When a task is done, tick it and strike it through: `- [x] ~~the task~~`.

Nothing here starts until Hari says **execute**.

## Decision first

- [x] ~~**Commit format from Week 5 on:** (A) `feat(w5p1): add stream endpoint` in each commit~~. **Chosen: A** (2026-10-27).

## Phase 0: before changing anything

- [x] ~~Save a snapshot of today's maps:~~ for W1–W4, every Part's cards and lines, and each run's START, END and step count. This is the "before" the finished work is compared against.

## Phase 1: bugs found in use

- [x] ~~**14. Calls inside `assert` lines.**~~ Hide only real checks: building the expected value (`ReadStats(records=2, malformed=1)`), `==` comparisons, and yes/no reads like `r.ok`. Keep the call being tested (`ok.to_row()`, `read_jsonl(path, stats)`). This fixes W4 Part 4's 5-step runs. (`page/flowmap.html`, `flowOnly`)
- [x] ~~**17. Yielded values show as answers**~~ (found while fixing 14). A generator's `yield`s are its output, but the recorder never saved them, so a streaming function's results never showed. Examples: `read_jsonl` (W4 Part 4), the W1 pipeline (`parse`, `keep`, `jsonl_chunks`), and W5's token streams. Each yielded value rides back to the code that asked for it, the card shows it, and END lists what was yielded. (`src/flowmap_tests/trace.py`, `src/flowmap_tests/build_project.py`, `page/flowmap.html`)
- [x] ~~**15. The map falling behind git.**~~ If a commit's update didn't run (for example from a sandboxed session), the next note says `map is behind: run flowmap.py update`. (`src/flowmap_tests/flowmap.py`, `note`)

## Phase 2: fixes from the review

- [x] ~~**11a.** The `transient` crash: read `transient`, `url` and `reason` only when the error class has them~~. (`src/flowmap_tests/trace.py`, `fields_of`)
- [x] ~~**11b.** Silent failures: log every test that couldn't be recorded, with the reason~~ ("failed", "needs Postgres running", "touches too few functions"). A Part left with no run is a problem in `build/check.txt`. (`src/flowmap_tests/pickruns.py`)
- [x] ~~**11c.** Real fake names: `MockTransport(handler=FlakyAPI)`, not always `ChaosAPI`~~. (`src/flowmap_tests/trace.py`)
- [x] ~~**11d.** Libraries worked out from what the code imports~~ (not the standard library, not your package, plus `asyncio`), instead of a fixed list. (`src/flowmap_tests/build_project.py`, `LIBS`)
- [x] ~~**11e.** Move the aiofetch summaries out of `build_project.py`~~ (`DESC`) into `cfg/w3.py` and `cfg/w4.py`.
- [x] ~~**11f.** Repo and practical paths in `cfg/` relative to the workspace~~ (`projects/aiofetch`), so a synced copy on Windows still works.
- [x] ~~**11g.** Cleanup after each build: remove `exports/` copies no Part or run uses, remove leftover check pages, keep `update.log` to its last 1,000 lines~~.
- [x] ~~**11h.** Cap a recording at 5,000 events, and prefer shorter runs when picking~~.

## Phase 3: ready for Weeks 5 to 21

- [x] ~~**1. Record through pytest itself,**~~ so fixtures, autouse setup, async tests and parametrize all work. Only the test's body is recorded, so fixture setup stays hidden. (`src/flowmap_tests/trace.py`, `src/flowmap_tests/pickruns.py`)
- [x] ~~**2. Find tests in subfolders:**~~ `tests/unit/`, `tests/integration/`, `tests/stage3/`, `tests/ops/`. (`src/flowmap_tests/pickruns.py`)
- [x] ~~**3. Parts from Conventional Commits:**~~ `feat(w7p1): …`, Stages `(w16s2)`, the bridge `(pf1p2)`; the old `Week N Part X: …` still works. Titles from `### Part N - …` and `## Stage N - …` headings. (`src/flowmap_tests/gitparts.py`)
- [x] ~~**4. Update after `git pull`**~~ too (a post-merge hook), because Parts are merged on GitHub. Re-run `hook` once per repo. (`src/flowmap_tests/flowmap.py`, `hook`)
- [x] ~~**5. A lane for every task and thread:**~~ `TaskGroup`, `create_task`, `gather`, `to_thread`, and FastAPI TestClient's thread. Then re-record W2. (`src/flowmap_tests/trace.py`)
- [x] ~~**6. Subpackages**~~ named by their full path (`adapters.alpha`), with one column per top-level subpackage. Python outside `src/` (`scripts/`, `examples/`) comes in through one settings line. (`src/flowmap_tests/trace.py`, `src/flowmap_tests/build_project.py`, `src/flowmap_tests/conds.py`)
- [x] ~~**7. A real network guard while recording:**~~ every non-local connection is refused, while local Postgres and Ollama still work. Drop the word filter that skipped offline OpenAI/Anthropic adapter tests. (`src/flowmap_tests/pickruns.py`, `src/flowmap_tests/trace.py`)
- [x] ~~**8. Several repos per week:**~~ each repo gets its own map entry (`W18 · llm-client-kit`, `W18 · aiofetch`), and a W18 commit in aiofetch doesn't touch W3/W4. (`cfg/`, `src/flowmap_tests/gitparts.py`)
- [x] ~~**9. Stubs without `TODO`**~~ (`raise NotImplementedError("Stage 1")`) count as not built; abstract methods stay. (`src/flowmap_tests/build_project.py`)
- [x] ~~**10. Fakes by name**~~ (`Mock…`, `Fake…`, `Stub…`, `Dummy…`) or a list in the settings. Drop "imported by nothing", which misfires on W7–W9. (`src/flowmap_tests/build_project.py`, `cfg/w3.py`, `cfg/w4.py`)
- [x] ~~**13. From Week 5, test code in the middle of a run shows**~~ in its own column, "from the test": a stand-in your code calls, a function the test hands in, a monkeypatched function. START stays your call and END stays its output. Weeks 1–4 stay as they are. (`page/flowmap.html`, `src/flowmap_tests/build_project.py`)

## Phase 4: safety net, so these bugs can't come back

- [x] ~~**12. Tool tests**~~ on tiny sample projects, run on every rebuild (`flowmap_tests/tests/`):
  - [x] ~~**Parts:**~~ each commit format finds the right Part (`Week N Part X`, `feat(w7p1)`, Stages, PF, a redo, a fix joining the Part before, in progress until `main` has it).
  - [x] ~~**Recorder:**~~ fixture tests, autouse, async, parametrize; an error class without `transient`; a fake's real name; `create_task`, `gather` and thread lanes; subpackages.
  - [x] ~~**Run filter:**~~ the call being tested inside an `assert` stays (the W4 Part 4 case); `r.ok`, `==` and expected values are hidden; test code in the middle shows from W5 and is hidden before; START is your first call; END is its output.
  - [x] ~~**Code scan:**~~ stubs count as not built; fakes are found by name.
- [x] ~~**16. Guards on the real map,**~~ on every rebuild and in the hook (`checks/`):
  - [x] ~~**Every run:**~~ START is a call of yours and END has an output.
  - [x] ~~**Every run:**~~ it doesn't lose most of the functions it really ran (this catches the 5-step kind of bug).
  - [x] ~~**Every run:**~~ every step shows something, and stepping back matches stepping forward.
  - [x] ~~**Every page:**~~ no overlapping words, no lines through cards, no card under a panel.
  - [x] ~~**Every page:**~~ no local paths, and no `#1` or "your code" text.
  - [x] ~~**Every Part:**~~ it has a run, or a stated reason why not.
  - [x] ~~**Saved snapshot:**~~ each week's summary is saved, so an old week changing unexpectedly is flagged. A change you intended is accepted with `flowmap.py build --accept`. (Saved in `build/expected.json`, so a commit in a project never touches the workspace's git.)
  - [x] ~~**Where problems show:**~~ in the commit note (`last check: 2 problems (see flowmap_tests/build/check.txt)`).

## Phase 5: finish

- [x] ~~Compare with the Phase 0 snapshot. W1–W4 should be identical, except W2's task lanes, W4's fake name and W4 Part 4's fixed runs.~~ W3 and W4 Parts 1–2 are identical. The rest changed only through fixes: calls on `assert` lines, yields, lanes, lines through `from package.module import`, W1 Part 5's new runs and `__hash__` in W1 Part 1. W4's fake name needed no change (its runs really use ChaosAPI).
- [x] ~~All checks green: tool tests, page check on every Part and run, real-mouse clicks, stepping back, panels.~~
- [x] ~~README updated: the commit format, the post-merge hook, the "from the test" column, the new checks. Also the rule: **a new bug gets a test before it's fixed.**~~
- [x] ~~Republish the map on claude.ai.~~
- [x] ~~Commit, merge, push, delete the branch.~~ Pushed as ff53f1c (2026-10-27).
- [x] ~~Hari re-runs `python3 flowmap_tests/src/flowmap_tests/flowmap.py hook <week>` once for `aiofetch` and `async-batch-fetcher` (adds the pull hook).~~ Done (2026-10-28); both hooks are in both repos.
- [x] ~~Tell the teaching session the commit format, and to run `flowmap.py update` after committing.~~ `HANDBOOK.md` has both (sections 2 and 5).

## Not doing (too much for a study tool)

- Drawing SQL, dbt or shell scripts: W12–W15 show only their Python.
- Starting Postgres, nginx or other services: the Part says what's missing instead.
- One map across several repos.
- A sandbox for running tests, a config format instead of `exec()`, or CI.
