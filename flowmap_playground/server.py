"""The flowmap playground: type an input on the page, press Run, and watch it travel START → END.

usage: python3 flowmap_playground/server.py [--port 8765]
       python3 flowmap_playground/server.py --refresh     bring every week up to its newest commit, then stop
                                                           (flowmap_tests' update runs it after each commit)

It serves a page on this machine only (127.0.0.1). A run records your input with flowmap_tests' recorder on the code of
the Part you picked, through that Part's entry in the week's driver (drivers/w4.py, its PARTS table), with the same
safety as the tests: no network beyond this machine, no API keys, an empty folder (so no .env of yours is read),
90 seconds at most. The map, the recorder, the
scanner and the page all come from flowmap_tests; your runs and this page live here, in runs/ and build/ (not in git).

It follows your commits as the tests map does. After a commit (or on the first page load after it), your saved runs
are played again on their Part's new code, each Part's Try: suggestions are made again from its tests (suggest.py),
and the week's map is rebuilt. A Run pressed on a page from before the commit asks you to reload it first.
"""

import argparse
import ast
import collections
import concurrent.futures
import contextlib
import fcntl
import glob
import hashlib
import importlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS_MAP = os.path.join(os.path.dirname(HERE), "flowmap_tests")
sys.path.insert(0, os.path.join(TESTS_MAP, "tools"))
import flowmap  # noqa: E402  (flowmap_tests/tools: settings, Parts, exports)
import pickruns  # noqa: E402  (the recording environment and the length cap)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import index  # noqa: E402  (what a commit's code holds, read without running it: Shrink, and any function's setup)
import suggest  # noqa: E402

KEEP = 20  # runs kept per week
HARVEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "harvest.py")
lock = threading.Lock()  # one run at a time
STALE = "Your code changed (a new commit) since this page loaded: reload the page"


def say(message):
    print(time.strftime("%H:%M:%S"), message, flush=True)


def driver_module(driver):
    """The driver as it is on disk now (an edit since the last load counts)."""
    folder = os.path.dirname(driver)
    for f in glob.glob(os.path.join(folder, "*.py")):  # by name: one loaded from another folder counts too
        sys.modules.pop(os.path.basename(f)[:-3], None)
    if folder in sys.path:
        sys.path.remove(folder)
    sys.path.insert(0, folder)
    return importlib.import_module(os.path.basename(driver)[:-3])


def table(driver, labels=()):
    """A driver's PARTS: per Part, its entries (label, hint) and its suggested inputs. Drivers import your project's
    code only inside their entries, so this Python (without the project's libraries) can read them. The driver of a
    week without its own (drivers/_auto.py) gives a row for each of `labels`."""
    module = driver_module(driver)
    blocks = {label: module.PARTS[label] for label in labels} if getattr(module, "ANY_PART", False) else module.PARTS
    return {part: {"entries": {name: {"label": e["label"], "hint": e.get("hint", "")} for name, e in block["entries"].items()},
                   "scenarios": [{"entry": s[0], "input": s[1], "kind": s[2], "about": s[3]} for s in block["scenarios"]]}
            for part, block in blocks.items()}


def projects(only=None):
    """Every week in flowmap_tests/cfg (or only those named), each with its driver: its own (drivers/w4.py), or
    drivers/_auto.py while it has none (a new week: "a function of yours" in every Part)."""
    os.chdir(TESTS_MAP)
    found = {}
    for cfg, c in flowmap.projects():
        if only and c["KEY"] not in only:
            continue
        driver = os.path.join(HERE, "drivers", c["KEY"].lower() + ".py")
        if not os.path.exists(driver):
            driver = os.path.join(HERE, "drivers", "_auto.py")
        try:
            labels = [x["label"] for x in flowmap.part_list(c)]
        except subprocess.CalledProcessError:  # its repo isn't there (yet)
            continue
        found[c["KEY"]] = {"cfg": os.path.join(TESTS_MAP, cfg), "c": c, "driver": driver, "parts": table(driver, labels)}
    return found


@contextlib.contextmanager
def build_lock():
    """One writer of runs/ and build/ at a time: this server, another one, or the refresh after a commit."""
    os.makedirs(os.path.join(HERE, "build"), exist_ok=True)
    with open(os.path.join(HERE, "build", ".lock"), "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def code_copy(c, commit):
    """flowmap_tests/exports/<commit>, made again from git when the tests map has deleted it (it keeps only the copies
    its Parts use). None when the commit is gone from git."""
    os.chdir(TESTS_MAP)
    try:
        return flowmap.export(c["REPO"], commit)
    except subprocess.CalledProcessError:
        shutil.rmtree(os.path.join(TESTS_MAP, "exports", commit), ignore_errors=True)  # export() made the folder first
        return None


def saved_runs(key):
    path = os.path.join(HERE, "runs", key, "index.json")
    return json.load(open(path)) if os.path.exists(path) else []


def save_runs(key, runs):
    json.dump(runs, open(os.path.join(HERE, "runs", key, "index.json"), "w"), indent=1, ensure_ascii=False)


# ---------------------------------------------------------------- your changes (Shrink), kept per week until Clear
def week_changes(key):
    """The week's changes: [{"fn": "lab.load", "name": "requests", "value": 20}], used by every run of the week."""
    path = os.path.join(HERE, "runs", key, "changes.json")
    return json.load(open(path)) if os.path.exists(path) else []


def save_changes(key, kept):
    os.makedirs(os.path.join(HERE, "runs", key), exist_ok=True)
    json.dump(kept, open(os.path.join(HERE, "runs", key, "changes.json"), "w"), indent=1, ensure_ascii=False)


def clear(key):
    """Clear: the week's runs use your code's own values again."""
    save_changes(key, [])


GONE = object()  # a change whose box you emptied on the page: the code's own value again


def merged(old, new):
    """Changes by function and name: a newer value replaces the older one; an emptied one goes. A pick (what you gave a
    function for a piece nothing else makes: "pick": true) is kept as the code you typed."""
    out = {(c["fn"], c["name"]): c for c in old}
    out.update({(c["fn"], c["name"]): c for c in new})
    return [{"fn": c["fn"], "name": c["name"], "value": c["value"], **({"pick": True} if c.get("pick") else {})}
            for c in out.values() if c["value"] is not GONE]


def value_of(change):
    """A change's value: "value" (from JSON), or "text" as you typed it on the page (20, [1, 2], "abc"; empty: none).
    A pick stays code: a value, or a call of yours (serving.running(lab.lab_app()))."""
    if "value" in change:
        return change["value"]
    if not str(change.get("text", "")).strip():
        return GONE
    if change.get("pick"):
        try:
            ast.parse(str(change["text"]).strip(), mode="eval")
        except SyntaxError:
            raise ValueError(f"{change.get('name')}: type a value or a call of yours") from None
        return str(change["text"]).strip()
    try:
        return ast.literal_eval(str(change.get("text", "")).strip())
    except (ValueError, SyntaxError):
        raise ValueError(f"{change.get('name')}: type a value, like 20, 0.5, \"text\" or [1, 2]") from None


INDEXES = {}  # code copy -> index.Index (a commit's code never changes)


def index_of(export):
    path = os.path.join(TESTS_MAP, export)
    if path not in INDEXES:
        INDEXES[path] = index.Index(path)
    return INDEXES[path]


def resolve(ix, kept):
    """The changes this code has: ([{"fn", "name", "code", "value"}], {file: [patch]}, [the names it doesn't have])."""
    applied, patches, missing = [], {}, []
    for c in kept:
        if c.get("pick"):
            continue  # used by setups(), not written into the code
        where = ix.locate(c["fn"], c["name"])
        if where is None:
            missing.append(f"{c['fn']} · {c['name']}")
            continue
        f, node = where
        applied.append({"fn": c["fn"], "name": c["name"], "code": ix.code(f, node), "value": c["value"]})
        patches.setdefault(f, []).append(ix.patch(f, node, c["value"]))
    return applied, patches, missing


def route(ix, text):
    """lab.main(requests=5): a name the function doesn't take goes to the nearest function below it that does (the
    call graph, breadth first). Returns (the call without those names, [changes])."""
    try:
        call = ast.parse(text.strip(), mode="eval").body
    except SyntaxError:
        return text, []
    if not isinstance(call, ast.Call):
        return text, []
    fn = ast.unparse(call.func)
    if fn not in ix.defs or ix.takes_any(fn):
        return text, []
    takes = {p for p, _ in ix.params(fn)}
    routed, keep = [], []
    for k in call.keywords:
        if k.arg is None or k.arg in takes:
            keep.append(k)
            continue
        try:
            value = ast.literal_eval(k.value)
        except ValueError:
            raise ValueError(f"{k.arg}: give it a plain value, like {k.arg}=5") from None
        routed.append(below(ix, fn, k.arg, value))
    if not routed:
        return text, []
    call.keywords = keep
    return ast.unparse(call), routed


def below(ix, start, name, value):
    """The change that gives `name` to the nearest function under `start` that takes it."""
    parent, frontier, found = {start: None}, [start], []
    while frontier and not found:  # one level at a time: the nearest level that has it
        nxt = []
        for fn in frontier:
            for callee in sorted(ix.calls.get(fn, ())):
                if callee not in parent:
                    parent[callee] = fn
                    nxt.append(callee)
                    if name in {p for p, _ in ix.params(callee)}:
                        found.append(callee)
        frontier = nxt
    if not found:
        raise ValueError(f"{start} doesn't take {name}, and nothing it calls does")
    if len(found) > 1:
        raise ValueError(f"{name} is taken by {' and '.join(found)}: give it to one of them, e.g. {found[0]}.{name}")
    target = found[0]
    callers, x = {}, target
    while parent[x] is not None:  # only the calls on the way down from `start`
        callers[x] = {parent[x]}
        x = parent[x]
    callers[start] = set()
    knobs = [o for o in ix.trace(ast.Name(id=name), target, name, callers) if "node" in o]
    if not knobs:
        raise ValueError(f"{start} gives {target} its {name} from something that isn't in the code; change it there")
    return {"fn": knobs[0]["fn"], "name": knobs[0]["name"], "value": value}


class NeedsSetup(ValueError):
    """A function of yours needs a piece nothing in your tests or your code makes. `ask`: those pieces, for the page to
    ask you ({fn, name, type}); your answer is kept like a change, until Clear."""

    def __init__(self, message, ask):
        super().__init__(message)
        self.ask = ask


def setups(ix, typed, tested, fakes, picks):
    """How to give your typed call what it needs (a method needs its object; a parameter you left out needs a value),
    in the order to try them, or None when it runs as typed:
      1. a test that reaches the function: it builds everything, and your values go in as the function starts;
      2. your code that calls it: the shortest way from a function that needs nothing (the call graph, breadth first);
      3. built from type hints: each piece made by its recipe (index.recipes: forward chaining).
    Raises NeedsSetup (4: the page asks you) when none can; when 1 or 2 might not get there and 3 can't build it, the
    ask is the last plan (run_plans raises it). `tested()`: what your tests passed into your code (harvest), read only
    when a setup is needed."""
    try:
        call = ast.parse(typed.strip(), mode="eval").body
    except SyntaxError:
        return None
    if not isinstance(call, ast.Call):
        return None
    fn = ast.unparse(call.func)
    kind = ix.kind(fn)
    if kind is None or "<" in fn or any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords):
        return None
    params = [p for p, _ in ix.params(fn)]
    if len(call.args) > len(params):
        return None  # Python says what's wrong
    code = {**dict(zip(params, call.args)), **{k.arg: k.value for k in call.keywords}}
    picked = {c["name"]: c["value"] for c in picks if c["fn"] == fn}
    missing = (["self"] if kind == "method" else []) + [p for p, d in ix.params(fn) if d is None and p not in code]
    if not missing:
        return None
    values = {}
    for p, node in code.items():
        try:
            values[p] = ast.literal_eval(node)
        except ValueError:
            values = None
            break
    plans, focus = [], {"fn": fn, "args": values or {}, "stop": True}
    startable = kind != "class" or ix.runs_code(fn)  # a pydantic model or an exception: no code of yours to start at
    if values is not None and not any(p in picked for p in missing) and startable:
        name, short = (ix.init_of(fn) or f"{fn}.__init__", fn.rsplit(".", 1)[-1]) if kind == "class" else (fn, None)
        plainest = sorted(tested(), key=lambda c: (not (c.get("end") or "").startswith("returned"), not c.get("direct")))
        reached = list(dict.fromkeys(c["test"] for c in plainest if c["fn"] == name and (short is None or c.get("makes", short) == short)))
        plans += [{"how": "test", "via": t, "focus": focus} for t in reached[:2]]
        way = ix.way_to(fn)
        if way:
            plans.append({"how": "caller", "via": " → ".join(way), "text": f"{way[0]}()", "focus": focus})
    given = {**{p: ast.unparse(n) for p, n in code.items()}, **picked}
    for text in ix.test_calls().get(fn, []):  # the values a test writes for it (LogRecord("t1", "ERROR", "db down"))
        written = ast.parse(text, mode="eval").body
        from_test = {**dict(zip(params, written.args)), **{k.arg: k.value for k in written.keywords}}
        if all(p in given or p in from_test for p in missing if p != "self"):
            given = {**{p: ast.unparse(v) for p, v in from_test.items()}, **given}
            break
    built, asks = ix.build(fn, given, fakes)
    if built:
        plans.append({"how": "built", "via": built, "text": built, "focus": {"fn": fn, "args": {}, "stop": False} if startable else None})
    if not built:  # 4: asked, now (nothing else to try) or after the ways above ran and none got there
        made = ix.recipes(fakes)
        what = [("its object (" + t + ")" if p == "self" else p + (f" ({t})" if t else "")) for p, t in asks]
        also = made.get(fn) if kind == "class" else None  # one your code or tests make another way
        tried = ", ".join(f"{p['how']} {p['via']}" for p in plans)
        why = f"the ways tried ({tried}) didn't get there" if plans else "no test reaches it, no code of yours calls it"
        ask = NeedsSetup(f"{fn} needs {', '.join(what)}: {why}, and nothing makes it. Give it below: a value, or a call of "
                         "yours" + (f" (or make one with {also})" if also else ""), [{"fn": fn, "name": p, "type": t} for p, t in asks])
        if not plans:
            raise ask
        plans.append({"how": "ask", "ask": ask})
    return plans


class TooLong(ValueError):
    """A run over the length the page can step through. `shrink`: the values in your code that made it long, each with a
    suggestion; `note`: when the length comes from your input instead (--jobs 300)."""

    def __init__(self, message, shrink=(), note=""):
        super().__init__(message)
        self.shrink, self.note = list(shrink), note


def shrink_values(ix, d, calls, text, way=()):
    """The values in your code that decide how long this run was: the most repeated calls' loops, traced back to a value
    in the code. Each: {fn, name, code, suggest, why, long (it made this run long), steps (an estimate, for a long one)}.
    Also a note when a length comes from your input instead. `way`: the unrecorded calls above the run's start when it
    was set up through your code (cli.main → cli.run), so a value can be traced back through them too."""
    ev = [e for e in d["events"] if e["k"] in ("call", "new")]
    by_id = {e["id"]: e for e in ev}
    pairs, per_fn, seen_callers = collections.Counter(), collections.Counter(e["fn"] for e in ev), {}
    for e in ev:
        up = by_id.get(e.get("parent"))
        if up:
            pairs[(up["fn"], e["fn"])] += 1
            seen_callers.setdefault(e["fn"], set()).add(up["fn"])
    for up, down in zip(way, way[1:]):
        seen_callers.setdefault(down, set()).add(up)
    knobs, notes = {}, []
    for (caller, callee), n in pairs.most_common():
        if n < 2:
            break
        for label, loop in ix.loops_around(caller, callee):
            for x in ix.counts(loop):
                for o in ix.trace(x, caller, label, seen_callers):
                    if "node" in o:
                        k = knobs.setdefault((o["fn"], o["name"]), {**o, "n": 0, "per": 0})
                        k["n"], k["per"] = max(k["n"], n), max(k["per"], n / max(per_fn[caller], 1))
                    elif "input" in o and n == pairs.most_common(1)[0][1]:
                        notes.append(f"the size comes from your input: {o['input']}" if o.get("option") or o["fn"] not in ix.defs
                                     else f"the size comes from what {o['fn']} was given: {o['input']}")
    typed = text.split()
    top = max((k["n"] for k in knobs.values()), default=0)
    out = []
    for (fn, name), k in sorted(knobs.items(), key=lambda kv: -kv[1]["n"]):
        if k.get("option") and name in typed:
            continue  # you typed --jobs: your input decides it, not the default
        code = ast.literal_eval(k["node"])
        suggestion, why = suggest_for(fn, name, code, calls)
        if suggestion is None:
            continue
        item = {"fn": fn, "name": name, "code": ix.code(k["file"], k["node"]), "suggest": suggestion, "why": why, "long": k["n"] == top}
        if item["long"]:
            size = (lambda v: v if isinstance(v, (int, float)) else len(v))
            item["steps"] = round(len(d["events"]) * size(suggestion) / max(size(code), 1))
        out.append(item)
    return out, "; ".join(dict.fromkeys(notes))


def suggest_for(fn, name, code, calls):
    """A smaller value for a knob: the one your tests give that function (the smallest), else a small one. None when
    nothing smaller makes sense (it's already small, or it isn't a size)."""
    if isinstance(code, bool) or isinstance(code, str) or code is None:
        return None, ""
    if isinstance(code, (int, float)):
        callee = name[:-1].split("(") if name.endswith(")") else None
        tested = sorted({c["args"][arg] for c in calls for arg in [callee[1] if callee else name]
                         if (c["fn"] == fn if not callee else c["fn"].rsplit(".", 1)[-1] == callee[0])
                         and type(c["args"].get(arg)) in (int, float) and 0 < c["args"][arg] < code})
        if tested:
            return tested[0], f"your test uses {tested[0]}"
        return (3, "a small value") if code > 3 else (None, "")
    if isinstance(code, (list, tuple, set, dict)) and len(code) > 2:
        return (list(code)[:2] if not isinstance(code, dict) else dict(list(code.items())[:2])), "the first 2 of them"
    return None, ""


def build(key, p, log=say):
    """That week's map from flowmap_tests, plus your runs, into build/proj_<key>.json."""
    os.chdir(TESTS_MAP)
    c = p["c"]
    for part in flowmap.part_list(c):
        flowmap.export(c["REPO"], part["commit"])
    runs = saved_runs(key)
    keep = [r for r in runs if code_copy(c, r["export"].split("/")[-1])]
    for r in runs:
        if r not in keep:
            log(f"{key}: your run {r['title']!r} is dropped: its commit {r['export'].split('/')[-1]} is gone from git")
            with contextlib.suppress(OSError):
                os.remove(os.path.join(HERE, "runs", key, r["file"]))
    if keep != runs:
        save_runs(key, keep)
    out = os.path.join(HERE, "build", f"proj_{key}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    r = subprocess.run([sys.executable, "tools/build_project.py", c["REPO"], "runs", out, p["cfg"], os.path.join(HERE, "runs", key)],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"building the {key} map failed: " + (r.stderr.strip().splitlines() or ["?"])[-1])
    return out


def row(p, part):
    """The driver's row a Part runs with: its own, or (a new Part nobody wrote a row for yet) the nearest one before
    it, so a new Part has entries and suggestions from its first commit. None when no row comes before it."""
    if part in p["parts"]:
        return part
    labels = [x["label"] for x in flowmap.part_list(p["c"])]
    earlier = [label for label in labels[: labels.index(part)] if label in p["parts"]] if part in labels else []
    return earlier[-1] if earlier else None


def rows(p):
    """Every Part's row, a new Part's borrowed from the Part before it."""
    out = {}
    for x in flowmap.part_list(p["c"]):
        if row(p, x["label"]):
            out[x["label"]] = p["parts"][row(p, x["label"])]
    return out


def with_suggestions(parts, made):
    """Each Part's Try: list: the ones made from its tests, or the driver's own when its tests gave none."""
    return {part: {**block, "scenarios": made.get(part) or block["scenarios"]} for part, block in parts.items()}


def page(all_projects, token):
    """The playground page: flowmap_tests' page with every week's map, your runs, and each Part's entries and suggested
    inputs. Returned for the server to keep: a second server writing build/ never changes the page this one serves."""
    os.chdir(TESTS_MAP)
    outs = [os.path.join(HERE, "build", f"proj_{k}.json") for k in all_projects]
    data = os.path.join(HERE, "build", "data.js")
    subprocess.run([sys.executable, "tools/combine.py", data, *outs], check=True)
    parts = {}
    for k, p in all_projects.items():
        try:
            made = {part: v["scenarios"] for part, v in json.load(open(os.path.join(HERE, "build", f"suggest_{k}.json"))).items()}
        except (OSError, ValueError):
            made = {}
        parts[k] = with_suggestions(rows(p), made)
    extra = {"token": token, "parts": parts, "changes": {k: week_changes(k) for k in all_projects}}
    open(data, "a").write("window.PLAYGROUND = " + json.dumps(extra) + ";\n")
    out = os.path.join(HERE, "build", "playground.html")
    subprocess.run([sys.executable, "tools/inject.py", "page/flowmap.html", data, out], check=True, capture_output=True)
    return open(out, "rb").read()


def play(p, part, entry, text, out=None, changes=()):
    """Your input through that Part's entry, recorded on that Part's code, with your changes (Shrink) made in the run's
    own copy of it. Returns the recording, with "export": the code it ran on, and "changes": the ones this code has.
    A ValueError says why there's none (TooLong: with the values that made it long). Kept at `out` if given."""
    os.chdir(TESTS_MAP)
    c = p["c"]
    chosen = next((x for x in flowmap.part_list(c) if x["label"] == part), None)
    if not chosen:
        raise ValueError(f"{c['KEY']} has no Part {part}")
    if entry not in p["parts"].get(row(p, part), {}).get("entries", {}):
        raise ValueError(f"{entry} isn't in {part if part.startswith('W') else 'Part ' + part}")
    export = code_copy(c, chosen["commit"])
    if not export:
        raise ValueError(f"Part {part}'s commit {chosen['commit']} is gone from git")
    keep = out is not None
    if not keep:
        fd, out = tempfile.mkstemp(prefix="flowmap-try-", suffix=".json")
        os.close(fd)
        os.remove(out)
    python = c.get("PYTHON") or os.path.join(c["REPO"], ".venv", "bin", "python")
    ix = index_of(export)
    typed, routed = route(ix, text) if entry == "call" else (text, [])
    kept = merged([{**x, "value": value_of(x)} for x in changes], routed)
    applied, patches, missing = resolve(ix, kept)
    plans = setups(ix, typed, lambda: harvest(c, chosen["commit"]), fakes(c), [x for x in kept if x.get("pick")]) if entry == "call" else None
    env = {**pickruns.safe_env(), **({"FLOWMAP_PATCHES": json.dumps(patches)} if patches else {})}
    d, yours, plan = run_plans(os.path.abspath(export), python, f"play:{p['driver']}:{row(p, part)}:{entry}", typed, plans, env, out)
    if not keep or len(d["events"]) > pickruns.MAX_EVENTS or not yours:
        os.remove(out)
    if not yours:
        if d["status"] == "passed" and entry == "call" and ix.kind(typed.split("(")[0].strip()) == "class":
            raise ValueError(f"{typed.split('(')[0].strip()}() runs none of your code: the class has no code of its own (its __init__ is Python's or a library's)")
        raise ValueError(d["status"].removeprefix("raised ValueError: ") if d["status"] != "passed" else "your code never ran")
    if len(d["events"]) > pickruns.MAX_EVENTS:
        way = plan["via"].split(" → ") if plan and plan["how"] == "caller" else ()
        found, note = shrink_values(ix, d, harvest(c, chosen["commit"]), typed, way)
        how = "Shrink has the values that made it long" if found else note or "try a smaller input"
        raise TooLong(f"too long to step through ({len(d['events'])} events): {how}", found, note)
    d["export"] = f"exports/{chosen['commit']}"
    d["changes"], d["routed"], d["missing"] = applied, routed, missing
    # kept for the week, but this Part's code has no such function or name (renamed since, or another Part's): not used
    d["note"] = f"not in this Part's code, so not used: {', '.join(missing)} (Clear removes it)" if missing else None
    d["setup"] = {"how": plan["how"], "via": plan["via"]} if plan else None
    return d


def run_plans(export, python, spec, typed, plans, env, out):
    """Record a run: as typed, or each way of setting it up in turn (setups) until one reaches your function in under
    5,000 events (a test with 100,000 records gives way to a smaller one). Returns (the recording, its calls of yours,
    the way used or None); the first run that was too long when no way is shorter."""
    long = None  # the first run that reached your function but is too long to step through
    for i, plan in enumerate(plans or [None]):
        last = i == len(plans or [None]) - 1
        if plan and plan["how"] == "ask":
            break
        if plan and plan["how"] == "test":  # the test that reaches your function, recorded from your function on
            cmd = [python, os.path.join(TESTS_MAP, "tools", "trace.py"), export, plan["via"], out]
        else:
            cmd = [python, os.path.join(TESTS_MAP, "tools", "trace.py"), export, spec, out, plan["text"] if plan else typed]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=90, env={**env, **({"FLOWMAP_FOCUS": json.dumps(plan["focus"])} if plan and plan["focus"] else {})})
        except subprocess.TimeoutExpired:
            if last and not long:
                raise ValueError("it ran for over 90 seconds; try a smaller input") from None
            continue
        if not os.path.exists(out):
            if last and not long:
                raise ValueError("the recorder crashed: " + ((r.stderr.strip().splitlines() or ["no message"])[-1])[:200])
            continue
        d = json.load(open(out))
        yours = [e for e in d["events"] if e["k"] in ("call", "new") and not e["fn"].startswith("test_playground.")]
        if yours and len(d["events"]) > pickruns.MAX_EVENTS and not last:
            if long is None:
                long = (d, yours, plan)
                os.replace(out, out + ".long")
            else:
                os.remove(out)
            continue
        if yours or (last and not long):
            if long:
                os.remove(out + ".long")
            return d, yours, plan
        os.remove(out)  # this way didn't reach your function: the next one
    if long:
        os.replace(out + ".long", out)
        return long
    raise plan["ask"]


def record(key, p, part, entry, text, changes=()):
    """Your input through that Part's entry, recorded on that Part's code, with the week's changes (and any sent with
    it, which are kept from now on). Returns the run (as the page plays it) and the node of its hidden "you" frame."""
    folder = os.path.join(HERE, "runs", key)
    os.makedirs(folder, exist_ok=True)
    kept = merged(week_changes(key), [{**x, "value": value_of(x)} for x in changes])
    save_changes(key, kept)
    name = time.strftime("%Y%m%d-%H%M%S") + f"-{entry}.json"
    d = play(p, part, entry, text, os.path.join(folder, name), kept)
    if d["routed"]:  # lab.main(requests=5): kept like the others
        save_changes(key, merged(kept, d["routed"]))
    runs = saved_runs(key)
    title = " ⏎ ".join(line.strip() for line in text.splitlines() if line.strip())
    runs.append({"file": name, "key": "play_" + name[:-5], "part": part, "export": d["export"],
                 "title": title if len(title) <= 60 else title[:59] + "…", "entry": entry, "input": text,
                 **({"changes": d["changes"]} if d["changes"] else {}), **({"setup": d["setup"]} if d["setup"] else {})})
    for old in runs[:-KEEP]:
        if os.path.exists(os.path.join(folder, old["file"])):
            os.remove(os.path.join(folder, old["file"]))
    save_runs(key, runs[-KEEP:])
    data = json.load(open(build(key, p)))
    you = {k: v for k, v in data["nodes"].items() if k.startswith("test_playground.")}  # the page may not know this entry yet
    return {**data["play"][-1], **({"note": d["note"]} if d["note"] else {})}, you


def follow(key, p, log=say):
    """Your saved runs, played again (the same entry, the same input) on their Part's newest code, as the tests map
    records its tests again after a commit. A run that can't run there any more stays on the code it was recorded on."""
    os.chdir(TESTS_MAP)
    commits = {x["label"]: x["commit"] for x in flowmap.part_list(p["c"])}
    runs, moved = saved_runs(key), 0
    for r in runs:
        now = commits.get(r["part"])
        if not now or r["export"] == f"exports/{now}":
            continue
        out = os.path.join(HERE, "runs", key, r["file"])
        try:
            play(p, r["part"], r["entry"], r["input"], out + ".new", r.get("changes", []))
        except ValueError as exc:
            log(f"{key} Part {r['part']}: your run {r['title']!r} stays on {r['export'].split('/')[-1]} ({exc})")
            continue
        os.replace(out + ".new", out)
        r["export"] = f"exports/{now}"
        moved += 1
    if moved:
        save_runs(key, runs)
        log(f"{key}: {moved} of your runs played again on the new code")


def harvest(c, commit, log=say):
    """What the tests at `commit` passed into your code (harvest.py), kept in build/harvest/ per commit."""
    stamp = hashlib.md5(open(HARVEST, "rb").read()).hexdigest()[:8]
    out = os.path.join(HERE, "build", "harvest", f"{commit}_{stamp}.json")
    if not os.path.exists(out):
        export = code_copy(c, commit)
        if not export:
            return []
        os.makedirs(os.path.dirname(out), exist_ok=True)
        python = c.get("PYTHON") or os.path.join(c["REPO"], ".venv", "bin", "python")
        try:
            r = subprocess.run([python, HARVEST, os.path.join(TESTS_MAP, export), out + ".tmp"], capture_output=True, text=True,
                               timeout=600, env=pickruns.safe_env())
        except subprocess.TimeoutExpired:
            log(f"{c['KEY']}: your tests at {commit} took over 10 minutes; no suggestions from them")
            return []
        if not os.path.exists(out + ".tmp"):
            log(f"{c['KEY']}: reading your tests at {commit} failed: " + ((r.stderr.strip().splitlines() or ["?"])[-1])[:200])
            return []
        os.replace(out + ".tmp", out)
    return json.load(open(out))["calls"]


def fakes(c):
    """The week's test fakes, and their old names (W4's FlakyAPI was ChaosAPI in Week 3)."""
    found = c.get("FAKES", [])
    return [*found, *(old for old, new in c.get("ALIASES", {}).items() if new in found)]


def suggestions(key, p, log=say):
    """Each Part's Try: suggestions, made from its tests (suggest.py) and played on its code. Kept in
    build/suggest_<key>.json, and made again only for a Part whose commit (or the drivers) changed."""
    os.chdir(TESTS_MAP)
    c, driver = p["c"], driver_module(p["driver"])
    path = os.path.join(HERE, "build", f"suggest_{key}.json")
    try:
        saved = json.load(open(path))
    except (OSError, ValueError):
        saved = {}
    stamp = hashlib.md5(b"".join(open(f, "rb").read() for f in [*sorted(glob.glob(os.path.join(HERE, "drivers", "*.py"))),
                                                                  suggest.__file__, HARVEST])).hexdigest()[:8]
    parts, out, todo = flowmap.part_list(c), {}, []
    for i, part in enumerate(parts):
        if not row(p, part["label"]):
            continue
        prev = parts[i - 1]["commit"] if i else None
        mark = f"{part['commit']}:{prev}:{row(p, part['label'])}:{stamp}"
        if saved.get(part["label"], {}).get("mark") == mark:
            out[part["label"]] = saved[part["label"]]
        else:
            todo.append((part["label"], part["commit"], prev, mark))
    if todo:
        commits = sorted({x for t in todo for x in t[1:3] if x})
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            calls = dict(zip(commits, pool.map(lambda x: harvest(c, x, log), commits)))
        private = [os.path.expanduser("~"), tempfile.gettempdir() + os.sep, TESTS_MAP]  # this machine's folders
        tries = {label: suggest.candidates(driver.PARTS[row(p, label)], calls[commit], calls[prev] if prev else [],
                                                fakes(c), private)
                 for label, commit, prev, _ in todo}

        def attempt(label, candidate):
            try:
                return play(p, label, candidate[0], candidate[1])
            except ValueError:
                return None

        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            runs = {(label, t): pool.submit(attempt, label, t) for label, ts in tries.items() for t in ts}
        for label, commit, prev, mark in todo:
            picked = suggest.choose([(t, runs[(label, t)].result()) for t in tries[label]])
            out[label] = {"mark": mark, "scenarios": picked}
            log(f"{key} Part {label}: {len(picked)} suggestion{'s' if len(picked) != 1 else ''} from your tests" if picked else
                f"{key} Part {label}: no suggestions from its tests yet")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(out, open(path, "w"), indent=1, ensure_ascii=False)
    return {label: v["scenarios"] for label, v in out.items()}


def signature(key, p):
    """What a week's playground is made from: its Parts' commits, the tests map's build of the week, the drivers and
    the playground's own code. A new commit (or a new tests map, or a driver edit) changes it."""
    os.chdir(TESTS_MAP)
    h = hashlib.md5(json.dumps([x["label"] + ":" + x["commit"] for x in flowmap.part_list(p["c"])]).encode())
    for f in [os.path.join(TESTS_MAP, "build", f"proj_{key}.json"), *sorted(glob.glob(os.path.join(HERE, "drivers", "*.py"))),
              os.path.abspath(__file__), suggest.__file__, HARVEST]:
        with contextlib.suppress(OSError):
            h.update(open(f, "rb").read())
    return h.hexdigest()


def refresh(found, log=say, suggest=True):
    """Bring each week up to its newest commit: your saved runs follow their Part's code, the Parts' suggestions are made
    from their tests, the map is rebuilt. A week that hasn't changed since its last refresh is skipped.
    Returns {week: its signature}."""
    built = {}
    with build_lock():
        for key, p in found.items():
            sig = signature(key, p)
            stamp = os.path.join(HERE, "build", f"stamp_{key}.txt")
            proj, listed = os.path.join(HERE, "build", f"proj_{key}.json"), os.path.join(HERE, "runs", key, "index.json")
            fresh = os.path.exists(proj) and os.path.getmtime(proj) >= (os.path.getmtime(listed) if os.path.exists(listed) else 0)
            if not (suggest and fresh and os.path.exists(stamp) and open(stamp).read() == sig):
                follow(key, p, log)
                if suggest:
                    suggestions(key, p, log)
                build(key, p, log)
                if suggest:
                    open(stamp, "w").write(sig)
            built[key] = sig
    return built


def current(server):
    """The page as of your newest commit: refreshed (once) when a week changed since this server built it."""
    found = projects(server.only)
    if {k: signature(k, p) for k, p in found.items()} != server.built:
        say("your code changed: updating the playground")
        server.built = refresh(found, suggest=server.suggest)
        server.projects = found
        server.page = page(found, server.token)
        say("the playground is up to date")


class Handler(BaseHTTPRequestHandler):
    def local(self):
        """A request for this server by its own name: a web page can't reach it through a borrowed name."""
        return self.headers.get("Host", "") in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")

    def reply(self, status, body, kind="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self.local():
            return self.reply(403, {"error": "not this server's name"})
        if self.path.split("?")[0] not in ("/", "/index.html"):
            return self.reply(404, {"error": "not found"})
        with lock:
            current(self.server)
        self.reply(200, self.server.page, "text/html; charset=utf-8")

    def do_POST(self):
        if not self.local() or self.path not in ("/play", "/clear") or self.headers.get("X-Flowmap-Token") != self.server.token:
            return self.reply(403, {"error": "only the playground's own page can ask for a run"})
        try:
            ask = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 10_000)))
            p = self.server.projects.get(ask.get("key"))
            if self.path == "/clear":
                if not p:
                    raise ValueError("there is no playground for that week")
                with lock, build_lock():
                    clear(ask["key"])
                    self.server.page = page(self.server.projects, self.server.token)
                return self.reply(200, {"changes": []})
            part, text = str(ask.get("part", "")), str(ask.get("input", ""))
            if not p:
                raise ValueError("there is no playground for that week")
            if not row(p, part):
                raise ValueError(f"Nothing to run at {part if part.startswith('W') else 'Part ' + part}")
            if ask.get("entry") not in p["parts"][row(p, part)]["entries"]:
                raise ValueError(f"{ask.get('entry')} isn't in {part if part.startswith('W') else 'Part ' + part} yet")
            if not text.strip() or len(text) > 2000:
                raise ValueError("type something to run (at most 2,000 characters)")
            with lock:  # one run at a time
                if signature(ask["key"], p) != self.server.built.get(ask["key"]):
                    return self.reply(409, {"error": STALE})
                sent = ask.get("changes") or []
                if not isinstance(sent, list) or not all(isinstance(x, dict) and {"fn", "name"} <= set(x) for x in sent):
                    raise ValueError("changes: a list of {fn, name, text}")
                with build_lock():
                    try:
                        run, nodes = record(ask["key"], p, part, ask["entry"], text, sent)
                    finally:  # the changes you sent are kept even when the run was too long
                        self.server.page = page(self.server.projects, self.server.token)
            self.reply(200, {"run": run, "nodes": nodes, "changes": week_changes(ask["key"]), "note": run.get("note")})
        except TooLong as exc:
            self.reply(400, {"error": str(exc), "shrink": exc.shrink, "note": exc.note, "changes": week_changes(ask["key"])})
        except NeedsSetup as exc:
            self.reply(400, {"error": str(exc), "ask": exc.ask, "changes": week_changes(ask["key"])})
        except ValueError as exc:
            self.reply(400, {"error": str(exc)})
        except Exception as exc:  # a bug here: say so on the page instead of hanging
            self.reply(500, {"error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, fmt, *args):  # quiet: one line per run instead of one per request
        if self.command == "POST":
            sys.stderr.write(time.strftime("%H:%M:%S ") + (fmt % args) + "\n")


class Server(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return  # the browser left (a reload, a closed tab): nothing to report
        super().handle_error(request, client_address)


def serve(port=8765, only=None, suggest=True):
    os.makedirs(os.path.join(HERE, "build"), exist_ok=True)
    found = projects(only)
    built = refresh(found, suggest=suggest)
    server = Server(("127.0.0.1", port), Handler)
    server.projects, server.only, server.suggest, server.built = found, only, suggest, built
    server.token = secrets.token_urlsafe(16)  # this server's secret: only its own page may ask for a run
    server.page = page(found, server.token)
    return server


def main():
    ap = argparse.ArgumentParser(description="type an input, watch it travel START → END")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--refresh", action="store_true", help="bring every week up to its newest commit, then stop")
    a = ap.parse_args()
    if not shutil.which("git"):
        raise SystemExit("needs git")
    if a.refresh:
        found = projects()
        refresh(found)
        print(f"playground up to date ({', '.join(found)})", flush=True)
        return
    server = serve(a.port)
    print(f"flowmap playground: http://127.0.0.1:{a.port}/  ({', '.join(server.projects)}; Ctrl+C stops it)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
