# The flowmap handbook

Everything needed to keep the flow maps working, week after week: what to do, when, and the rules. It's for Hari and for any Claude session that works on a week's project or on flowmap itself.

The details behind each part are in [`README.md`](README.md) (the tests map) and [`../flowmap_playground/README.md`](../flowmap_playground/README.md) (the playground).

## 1. The two maps

| | Tests map (`flowmap_tests/`) | Playground (`flowmap_playground/`) |
|---|---|---|
| Shows | Each Part's code, and runs recorded from the tests that Part added | The same map, with runs of inputs you type |
| Open it | `flowmap_tests/build/flowmap.html` in a browser | `python3 flowmap_playground/server.py`, then the link it prints (`http://127.0.0.1:8765/`) |
| Updates | By itself after each commit and each `git pull` (git hooks) | Your runs: whenever you press Run. The map: when the server starts |
| Shared copy | https://claude.ai/artifact/9riLY9Q6oGWwu4yECNCq3X (only when Claude republishes it) | None: it needs Python on your machine |
| Holds the shared code | Yes: the recorder, the scanner and the page live here | No: it uses `flowmap_tests`' code |

Both read your project repos only through `git archive` copies. They never change your code or your working tree.

## 2. Each week, start to finish

### Before you start Part 1

1. **Know where the week's code lives:** a repo you already have (W4 carried on in `aiofetch`) or a new one (W5 starts `stream-svc`).
2. **A new repo needs this layout:**
   - the code in `src/<package>/` with an `__init__.py`;
   - the tests anywhere under `tests/`;
   - its own `.venv` with Python 3.12 or newer and pytest. Add pytest-asyncio if the tests are `async def`.

### Part 1

3. **Commit Part 1** with the Part in the message: `feat(w5p1): add the stream endpoint`.
4. **Add the week to the map** (once per week). Ask Claude to "add week 5 to the map", or run:

   ```
   python3 flowmap_tests/tools/flowmap.py init W5 projects/stream-svc --week 5 --practical <the week's practical .md>
   ```

   - It needs at least one commit that names a Part (step 3), or it stops and says so.
   - The practical gives the Parts their titles (`### Part 2 - …`) and lists the Parts not started yet.
5. **A new repo needs the git hooks**, and only Hari can install them (Claude isn't allowed to):

   ```
   python3 flowmap_tests/tools/flowmap.py hook W5
   ```

   It installs the hook for after a commit and the hook for after a `git pull`. Running it again is always safe: it fixes a hook that points at an old folder.
6. **The playground gets the week:** Claude writes `flowmap_playground/drivers/w5.py`. Its `PARTS` table lists, for each Part:
   - its entries: how your input reaches that Part's code, with its fake;
   - 2–4 suggested inputs: a good one, a bad one, and up to two more. Together they reach every component that Part has, and each has a one-line description.

   `flowmap_playground/tests/test_scenarios.py` must pass. A component that no input can reach yet (starter code a later Part starts using) needs a `"not yet"` note with its reason in that Part's row, and only Hari decides when a note is OK. Then restart the server (section 4).
   - **Every new Part gets its row** in the table too, or the box says "Nothing to run" at that Part.
7. **Check once:** `python3 flowmap_tests/tools/flowmap.py build --check` should end with `ok` in `flowmap_tests/build/check.txt`. Then open the map and look at Part 1: START should be your first call, and END what it gave back.

### Every Part

8. **Commit with the Part in each message:** `feat(w5p2): …`, `fix(w5p2): …`, `test(w5p2): …`. See [Commits](#commits).
9. **The Part's tests become its runs.** At least one new test must go through 3 or more of your functions. See [Tests](#tests).
10. **Merge it into `main` when it's finished.** Until then it shows as *in progress* (a dashed pill). From Week 7, Parts are merged on GitHub; `git pull` them, and the pull hook updates the map. A `git pull --rebase` doesn't run that hook, so run `flowmap.py update` after one.

### After every commit (and every `git pull`)

11. **Read the one line the hook prints**, for example:

    ```
    flowmap: W5 Part 2 added · Second endpoint · updating build/flowmap.html in the background · last check: ok
    ```

    - `last check: 2 problems (see flowmap_tests/build/check.txt)`: read that file. Section 6 says what each problem means.
    - `the map was behind for W5`: an earlier update didn't run. This one catches up.
12. **A commit made from a sandboxed session (like a Claude session) may skip the hooks.** Then run this right after committing:

    ```
    python3 flowmap_tests/tools/flowmap.py update
    ```

    Use `update`, not `build`: only `update` (and `build --check`) runs the checks.
13. **Refresh the page** to see the change. The map takes about a minute to rebuild.

### At the end of the week

14. **Make sure everything is merged into `main`** and the last check says `ok`.
15. **Ask Claude to republish the claude.ai link** if you want the shared copy up to date.
16. **Run the portfolio sync** in `ai-eng-projects` (it commits; you push):

    ```
    cd ai-eng-projects && ./sync.sh && git push
    ```

    It copies `flowmap_tests/` and the playground's code (not your playground runs or its built page).

### Special weeks

| Week kind | What's different |
|---|---|
| Several repos in one week (W18 builds `llm-client-kit` and changes `aiofetch`) | One `init` per repo, each with its own key: `init W18-llm projects/llm-client-kit --week 18` and `init W18-aiofetch projects/aiofetch --week 18`. Each gets its own entry in the menu. A W18 commit in `aiofetch` never changes W3 or W4 |
| Stages instead of Parts (W16–W17) | Commit with `(w16s2)`. The pill says `S2`, and its title comes from `## Stage 2 - …` |
| The production bridge (PF-1 to PF-3) | Commit with `(pf1p2)`, and `init` with `--week PF1` |
| SQL and dbt weeks (W12–W15) | Only the Python shows. SQL, dbt and shell scripts aren't drawn |
| Code outside `src/` (`scripts/`, `examples/`) | One line in the week's cfg: `CODE_DIRS = ["scripts"]` |
| Tests that need Postgres or another service | Start it yourself. Local services work while recording; a test whose service isn't running gets no run, and `check.txt` says why |

## 3. Keeping the tests map up to date

**What happens by itself:** after each commit and each `git pull`, the hook runs `flowmap.py note` (the one line), then `flowmap.py update` in the background. `update` does the following:

1. finds the Parts from the commit messages;
2. copies each Part's commit into `flowmap_tests/exports/`;
3. records the tests each new Part added;
4. rebuilds every week's map;
5. runs every check (section 6) and writes `flowmap_tests/build/check.txt`. The log goes to `flowmap_tests/build/update.log`.

**What doesn't update by itself:**

| What | What to do |
|---|---|
| A week before `init` has run for it | Run `init` (section 2, step 4) |
| A repo without hooks | Run `hook <week>` once (Hari) |
| A commit from a sandboxed session | Run `flowmap.py update` after committing |
| The claude.ai link | Ask Claude to republish it |
| The open page | Refresh it |

**Runs stay the same unless the code changes.** A Part's runs are recorded once and kept until that Part's commit changes. When the recorder itself changes, the same tests are recorded again, so a Part's stories don't switch.

## 4. Keeping the playground up to date

- **Start it:** `python3 flowmap_playground/server.py`. Stop it with Ctrl+C.
- **What it runs:** the Part selected in the top bar, on that Part's own code, through that Part's entry. **Try:** fills the box with one of that Part's suggestions; you press Run.
- **When it rebuilds:** at start, it builds every week that has a driver.
  - **After a new Part or a new week, restart it** and reload the page. The page's map comes from when the server started.
- **Your runs:** the last 20 per week are kept in `flowmap_playground/runs/<week>/`. They never go into git, sync or the tests map.
- **A new week:** it has no input box until its driver exists (section 2, step 6).
- **An entry point that changes in a later Part** (a renamed function, a new argument): the driver needs that Part's row updated. `python3 -m unittest discover -s flowmap_playground/tests` fails and names the week and Part. Run these tests after any change to a driver or to the shared code.
- **Two servers at once** (yours on 8765, a check on another port) each keep their own page and secret. Claude uses `--port 8798` for checks and stops only that one.

**What you can type, for example:**

| Week | Entry | Input |
|---|---|---|
| W4 | `python -m aiofetch` | `/v2/items/7`, or `/items/1=503,503,200` (`=` scripts the fake's answers) |
| W4 | `client.get_item` | `7 1500 3007` |
| W4 | `fetch → write → read jsonl` | `/items/1 /items/2`, or add `torn` for a half-written line |
| W3 | `client.fetch_many` | `/items/1 /items/3=404` |
| W2 | `async-batch-fetcher` | `--jobs 5 --fail-every 3` |
| W1 | `logparse` | `--level WARNING` (log lines below it with Shift+Enter, or none for the sample log) |

## 5. The rules

### Commits

- **Name the Part in every commit:** `type(wNpX): what it adds`, all lowercase in the scope.
  - Any type works: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`. A `!` (`feat(w5p1)!:`) is fine too.
  - A Stage is `(w16s2)`; the production bridge is `(pf1p2)`.
  - The older `Week 5 Part 1: …` still works.
- **A commit that names no Part** joins the Part before it.
- **A squash merge's ` (#12)`** is dropped from the title.
- **A lettered Part** (`pA`, warm-up work) folds into Part 1.
- **A Part's code is its last commit.**
- **The newest Part is in progress** until `main` contains it.

### Tests

A Part's runs are picked from the tests that Part added. For a test to become a run:

- **Where:** it sits anywhere under `tests/`, in a `test_*.py` file. It's a `test_…` function, or a method of a `class Test…`.
- **Kinds:** fixtures, autouse setup, `async def` and parametrize all work. Only the test's body is recorded, and a parametrized test runs its first case.
- **It passes** on that Part's commit.
- **It goes through at least 3 of your functions.** A test that only checks one value tells no story.
- **It's short enough:** under 5,000 events and under 90 seconds.
- **The best two are kept:** the ones that go through the most of your functions, from different test files, and the shorter run when two are equal.

A Part with no test like that is still on the map, without a run. `check.txt` has a `note:` line saying why.

### Asserts

- **Write each check on one line with `assert`.** A check that spans lines, or uses `self.assertEqual`, can show up in a run.
- **What stays visible:** the call being tested, even on an `assert` line (`assert ok.to_row() == {...}`).
- **What's hidden:** building the expected value, comparisons (`==`, `<`, `in`, `len`, `bool`) and yes/no reads like `r.ok`.

### Code

- **A starter stub** (`raise NotImplementedError`, with or without a `# TODO`) isn't built yet. It joins the map in the Part that fills it in. An abstract method (`@abstractmethod`, or one on an `ABC` or `Protocol`) stays.
- **A test fake** is a class named `Mock…`, `Fake…`, `Stub…` or `Dummy…` (`FakeTransport`). A fake with another name goes in the cfg's `FAKES` list (`FAKES = ["flaky.FlakyAPI"]`).
- **A card's summary** is the first line of the function's docstring. Without a docstring, the cfg's `EXTRA_DESC` can give one.
- **Subpackages:** each is named by its path (`adapters.alpha`), and each top-level subpackage gets one column.
- **Weeks 1–4:** test code never shows.
- **From Week 5:** test code that your code calls in the middle of a run (a stand-in, a function the test hands in, a monkeypatched function) shows in the **from the test** column. START is always your first call, and END its output.

### Safety

- **While recording**, both for tests and for the playground:
  - every connection that isn't to this machine is refused;
  - `*_API_KEY` and `*_TOKEN` are removed, and every proxy points at a closed port;
  - so no test can spend money on a paid API.
- **What still works:** local Postgres or Ollama.
- **Recordings hold real values.** Don't record tests that read secrets or private files.
- **The playground** runs your code in an empty throwaway folder, so it never reads your `.env`. W4 gets a fake key.
- **Your playground server** only listens on 127.0.0.1, and only runs for its own page.
- **Never commit `.env`.**
- **The page never shows a local path, a numbered object (`ReadStats#1`) or "your code".** The checks fail if it does, and Claude scans for local paths before every republish.

### For Claude sessions working on flowmap

- **Plan first.** Write the plan as a checklist file and strike items through as they're done. Change nothing until Hari says **execute**.
- **A new bug gets a test before it's fixed.** The test must fail first, for the right reason.
- **Keep it a study tool:** no extra features, layers or config formats. Build a bicycle when a bicycle does the job.
- **Old weeks must not change by themselves.** If a tool change alters an old week (`check.txt`: "changed by itself"), find out why. Accept it with `build --accept` only when the change is a fix you can explain.
- **When `trace.py` records differently**, raise `RECORDER` in `tools/pickruns.py`. The same tests are then recorded again.
- **Before finishing a change:**
  - `build --check` says `ok`;
  - the tool tests pass (`python3 -m unittest discover -s flowmap_tests/tests`);
  - if shared code or a driver changed, the playground tests pass too.
- **Never install git hooks:** Hari runs `hook`.
- **Never edit Hari's project code** for the map. Drivers and flowmap code live in flowmap.
- **Commit or push only when asked:**
  - branch first, then commit, merge into `main` with `--ff-only`, push, and delete the branch;
  - commit only flowmap files, never Hari's other files (notebooks, teaching-style, interview notes);
  - end the commit message with the attribution lines.
- **Leave `ai-eng-projects/README.md` to the course session.**

### If you change the page

These are Hari's look rules. Each one came from his feedback.

- **Palette:** "Ice" on pure black.
  - Ice blue for your calls and waiting lines, mint for answers, red for errors.
  - Parallel tasks and threads in white, orange, lime and pale yellow.
  - Grey for things at rest. No purple or navy.
- **Boxes:** rounded corners, thin lines. No bounce, no bubbly chips.
- **Words:** as few as possible. File names only, never full paths. Words never overlap.
- **START and END:** START is what you call; END is what that call gave back.
- **"You"** appears only on START, in the caption before the run starts, and in FROM / BACK TO for a call you made.
- **Steps:** every step shows something. Stepping back returns the map exactly to how it was.
- **The details box** never hides a value: no cut names, no folded short lists. It can be resized from its left edge, bottom edge and corner, and reset to 300px wide, full height.
- **→ / ← always step the run,** except while typing in a text box.

## 6. The checks, and what to do when one fails

`build --check` and the hooks run these. Problems go to `flowmap_tests/build/check.txt` and into the next commit's note.

| `check.txt` says | It means | What to do |
|---|---|---|
| `START is not a call of yours` / `END shows no output` | A run doesn't start or end with your code | A bug: write a test for it, then fix it |
| `shows 2 of the 5 functions it ran` | The map hides most of a run (the old "Part 4 has only 5 steps" kind of bug) | A bug: test, then fix |
| `step 12 … shows nothing` / `looks different reached backward` | Stepping is broken | A bug: test, then fix |
| `overlaps` / `through cards` / `cards under a panel` | Words on top of each other, lines through cards, cards hidden by a panel | Fix the layout |
| `the page shows "…/home/…"`, `"ReadStats#1"` or `"your code"` | Words the page must never show | Fix where the value comes from |
| `W2 Part 3 changed by itself` | An old week changed although its code didn't | If it's an intended fix, `build --accept`. If not, it's a bug |
| `note: W1 Part 5: no run (touches only 1 of your functions)` | Not a problem: the Part's tests tell no story | Add a test that goes through more of the Part, if you want a run |
| `tool test FAIL: …` | flowmap's own tests failed | Fix them before anything else |

## 7. Commands

| Command (from `ai_eng_workspace/`) | What it does |
|---|---|
| `python3 flowmap_tests/tools/flowmap.py build` | Rebuild every map (no checks) |
| `python3 flowmap_tests/tools/flowmap.py build --check` | Rebuild, then run every check |
| `python3 flowmap_tests/tools/flowmap.py build --accept` | The same, then save this map as the expected one |
| `python3 flowmap_tests/tools/flowmap.py update` | What the hooks run: build and check, quietly |
| `python3 flowmap_tests/tools/flowmap.py note` | The one line the hooks print |
| `python3 flowmap_tests/tools/flowmap.py hook W5` | Install or repair the hooks in that week's repo (Hari only) |
| `python3 flowmap_tests/tools/flowmap.py init W5 projects/x --week 5 --practical plan.md` | Add a week to the map |
| `python3 flowmap_playground/server.py [--port 8766]` | Start the playground |
| `python3 -m unittest discover -s flowmap_tests/tests` | The tool tests (a rebuild also runs them when the tools changed) |
| `python3 -m unittest discover -s flowmap_playground/tests` | The playground tests: every suggestion of every Part, the server, the page (about two minutes; needs Chrome and node) |
| `node flowmap_tests/checks/clicks.mjs file://$PWD/flowmap_tests/build/flowmap.html#W4` | Real mouse clicks on every column of a week. The same for `resize.mjs` (resizing the details box) and `keys.mjs` (→ / ← step from anywhere) |

## 8. A week's settings file (`flowmap_tests/cfg/<key>.py`)

`init` writes the first five lines. Everything else is optional.

| Setting | What it's for |
|---|---|
| `KEY, NAME, WEEK` | The map's key (`W5`, `W18-aiofetch`), the project's name, the week (`W5`, `PF1`) |
| `REPO` | The repo, relative to the workspace (`projects/aiofetch`) |
| `WEEK_NUM, PRACTICAL` | The week (5, or `"PF1"`) and the practical's path (titles and Parts not started yet) |
| `PYTHON` | A Python other than the repo's `.venv/bin/python` |
| `CODE_DIRS` | Your Python outside `src/`: `["scripts"]` |
| `FAKES` | Test fakes whose name doesn't say so: `["flaky.FlakyAPI"]` |
| `EXTRA_DESC` | Card summaries for functions without a docstring |
| `MAP` | Columns set by hand (W3 and W4 have one). Without it, the columns are worked out |
| `RUN_META` | Runs picked by hand instead of the automatic pick |
| `PARTS`, `COMMIT`, `BRANCH` | Parts listed by hand, for a repo whose commits don't name Parts (W1) |
| `ALIASES` | One identity for a function that moved or was renamed (W4: ChaosAPI → FlakyAPI) |
| `LINE_LABELS`, `CORE`, `GOAL` | Fine-tuning for a hand-set map (see `cfg/w3.py`) |

## 9. Where things live

| Path | What it is |
|---|---|
| `flowmap_tests/tools/` | `flowmap.py` (the only command you run), `trace.py` (the recorder), `pickruns.py` (picks each Part's runs), `build_project.py` (the scanner), `gitparts.py` (Parts from commits) |
| `flowmap_tests/page/flowmap.html` | The page both maps use |
| `flowmap_tests/cfg/` | One settings file per week |
| `flowmap_tests/runs/` | Recorded test runs (in git) |
| `flowmap_tests/checks/` | The page checks: `smoke.js` (every rebuild), and the real-mouse checks |
| `flowmap_tests/tests/` | The tool tests, the sample project, and a sample week built through the whole pipeline |
| `flowmap_tests/build/`, `exports/` | The built page, data, logs, check results and Part copies (not in git) |
| `flowmap_tests/PLAN.md`, `flowmap_playground/PLAN.md` | The checklists the two were built from |
| `flowmap_playground/server.py`, `drivers/` | The playground and how your input reaches each week |
| `flowmap_playground/runs/`, `build/` | Your playground runs and its page (not in git, not synced) |

## 10. When something goes wrong

| What you see | Why | What to do |
|---|---|---|
| A new Part isn't on the map | The hook didn't run (a sandboxed session), or the message doesn't name the Part | Run `flowmap.py update`; check the message format |
| A new week isn't in the menu | `init` hasn't run for it | Run `init` |
| A commit prints "can't open file …/flowmap/tools/flowmap.py" | The hook points at an old folder | Run `hook <week>` again |
| `init` says "no commits like feat(w5p1)" | No commit names a Part yet | Commit Part 1 with `feat(w5p1): …` first |
| A Part has no run | Its new tests don't qualify (see `check.txt`) | Add a test that goes through 3 or more of your functions |
| A check from the test shows in a run | The assert spans several lines, or uses `self.assertEqual` | Put the assert on one line with `assert` |
| A fake sits with the real code | Its name doesn't say "fake" | Add it to `FAKES` |
| A function only appears in a later Part | It was a starter stub until then | Nothing: that's the Part that built it |
| The playground says "too long to step through" | Over 5,000 events | A smaller input |
| The playground's map misses the newest Part | The server was started before that commit | Restart `server.py` and reload |
| The playground says "Nothing to run at Part 3" | The week's driver has no row for that Part | Ask Claude to add it (entries and suggestions) |
| The claude.ai link shows an old map | It's a copy | Ask Claude to republish it |

When asking Claude for a fix, give the week, Part, run and step, plus a screenshot. For example: "W4 Part 3, run 1, step 14: the box cuts off a value".
