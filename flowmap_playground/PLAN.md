# flowmap_playground plan: type an input, watch it travel START → END

When a task is done, tick it and strike it through: `- [x] ~~the task~~`.

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
- [ ] Hari re-runs `python3 flowmap_tests/tools/flowmap.py hook W2` and `hook W4`: the old hooks point at `flowmap/`.
