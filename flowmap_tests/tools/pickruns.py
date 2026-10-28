"""Pick each Part's story runs automatically: the tests that Part added, recorded on that Part's own code, best two kept.

A test is a candidate when it is new in the Part (by file and name), anywhere under tests/. pytest runs it, so
fixtures, async tests and parametrize work. Recording runs with API keys removed, every proxy pointed at a closed
port, and every connection that isn't to this machine refused, so a test that tried the real network fails instead
of spending money. The best runs are the ones that pass through the most of the project's own functions. Results are kept in runs/auto/<project>/<part>/ and reused while the Part's commit is the same.
"""

import ast
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
TRACE = os.path.join(HERE, "trace.py")
MAX_EVENTS = 5_000  # a longer recording is too long to step through


def test_functions(export):
    """(file under the export, pytest name) for every test: tests/unit/test_a.py, TestCase::test_b."""
    out = set()
    for d, subs, files in os.walk(os.path.join(export, "tests")):
        subs[:] = sorted(x for x in subs if x != "__pycache__")
        for f in sorted(files):
            if not (f.startswith("test_") and f.endswith(".py")):
                continue
            path = os.path.join(d, f)
            try:
                tree = ast.parse(open(path, encoding="utf-8").read())
            except SyntaxError:
                continue
            for n in tree.body:
                inner = [(f"{n.name}::", m) for m in n.body] if isinstance(n, ast.ClassDef) and n.name.startswith("Test") else [("", n)]
                for prefix, fn in inner:
                    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name.startswith("test_"):
                        out.add((os.path.relpath(path, export), prefix + fn.name))
    return out


def safe_env():
    env = {k: v for k, v in os.environ.items() if not (k.endswith("_API_KEY") or k.endswith("_TOKEN"))}
    dead = "http://127.0.0.1:9"
    env.update(HTTP_PROXY=dead, HTTPS_PROXY=dead, ALL_PROXY=dead, http_proxy=dead, https_proxy=dead, NO_PROXY="localhost,127.0.0.1,::1")
    env["PYTHONHASHSEED"] = "0"  # hash() values (a record used as a dict key) come out the same every recording
    return env


def title(fn):
    words = fn[len("test_"):].replace("_", " ").strip()
    words = words[:1].upper() + words[1:]
    return words if len(words) <= 42 else words[:41].rsplit(" ", 1)[0] + "…"


RECORDER = 6  # raise it when trace.py records differently: saved runs are recorded again (the same tests)


def score(path):
    """(how many of the project's functions the run passes through, its length), or (None, why it can't be used)."""
    d = json.load(open(path))
    if d.get("status") != "passed":
        return None, d.get("status", "failed")[:140]
    if len(d["events"]) > MAX_EVENTS:
        return None, f"too long ({len(d['events'])} events)"
    # yours: not under tests/ (a dataclass's made __init__ has no file: it counts by its module's name)
    own = {e["fn"] for e in d["events"] if e["k"] in ("call", "new") and not ((e.get("def") or {}).get("file") or "").startswith("tests/")
           and not e["fn"].split(".")[0].startswith("test_")}
    if len(own) < 3:  # a test that barely touches the project tells no story
        return None, f"touches only {len(own)} of your functions"
    return len(own), len(d["events"])


def record(export, f, name, folder, python, code_dirs):
    """Record one test: (score, length, out file), or (None, why not, None)."""
    out = os.path.join(folder, f"{os.path.relpath(f, 'tests')[:-3].replace(os.sep, '__')}__{name.replace('::', '__')}.json")
    env = {**safe_env(), "FLOWMAP_CODE_DIRS": ",".join(code_dirs)}
    try:
        r = subprocess.run([python, TRACE, export, f"{f}::{name}", out], capture_output=True, text=True, timeout=90, env=env)
    except subprocess.TimeoutExpired:
        return None, "took over 90 s", None
    if not os.path.exists(out):
        return None, "the recorder crashed: " + ((r.stderr.strip().splitlines() or ["no message"])[-1])[:120], None
    s, size = score(out)
    if not s:
        os.remove(out)
        return None, size, None
    return s, size, out


def pick(project, label, commit, export, prev_export, python, keep=2, limit=40, log=print, code_dirs=()):
    folder = os.path.join("runs", "auto", project, label)
    index = os.path.join(folder, "index.json")
    if os.path.exists(index):
        saved = json.load(open(index))
        if saved.get("commit") == commit and saved.get("recorder") == RECORDER:
            return saved
        if saved.get("commit") == commit and saved["picked"]:
            # the recorder changed, the code didn't: record the same tests again, so a Part's stories stay the same
            again = [record(export, p["test"], p.get("name", p["fn"]), folder, python, code_dirs) for p in saved["picked"]]
            if all(a[0] for a in again):
                saved.update(recorder=RECORDER, picked=[{**p, "score": a[0]} for p, a in zip(saved["picked"], again)])
                json.dump(saved, open(index, "w"), indent=1)
                log(f"  Part {label}: recorded its {len(again)} runs again")
                return saved
    os.makedirs(folder, exist_ok=True)
    new = sorted(test_functions(export) - (test_functions(prev_export) if prev_export else set()))[:limit]
    found, skipped = [], []
    for f, name in new:
        s, size, out = record(export, f, name, folder, python, code_dirs)
        if s:
            found.append((s, f, name, out, size))
        else:
            skipped.append([f"{f}::{name}", size])
            log(f"  skip {f}::{name} ({size})")
    found.sort(key=lambda r: (-r[0], r[4], r[1], r[2]))  # most of your functions first; then the shorter run
    # the best run first; after it, prefer runs from other test files, so the Part tells more than one story
    best = []
    for r in found:
        if len(best) < keep and (not best or r[1] not in {b[1] for b in best}):
            best.append(r)
    best += [r for r in found if r not in best][: keep - len(best)]
    picked = [{"file": os.path.relpath(out, "runs"), "test": f, "name": name, "fn": name.split("::")[-1], "title": title(name.split("::")[-1]), "score": s}
              for s, f, name, out, _ in best]
    for r in found:
        if r not in best:
            os.remove(r[3])
    if not new:
        skipped.append(["", "the Part added no tests"])
    saved = {"commit": commit, "recorder": RECORDER, "picked": picked, "skipped": skipped}
    json.dump(saved, open(index, "w"), indent=1)
    log(f"  Part {label}: {len(new)} new tests, {len(found)} told a story, kept {len(picked)}")
    return saved
