"""Turn one project's git history and recorded runs into the map's data.

usage: python3 build_project.py <repo> <runs_dir> <out.json> <project_config.py>
Settings that are missing are worked out: the Parts from commit messages (tools/gitparts.py), the runs from
runs/auto/ (tools/pickruns.py), summaries from docstrings, fakes and assert-only calls from the code and the runs,
and a column for every function the settings don't place.
"""

import ast
import hashlib
import json
import os
import re
import subprocess
import sys

REPO, RUNS, OUT, CFG = sys.argv[1:5]
PLAY_DIR = sys.argv[5] if len(sys.argv) > 5 else None  # flowmap_playground's runs: your inputs, kept apart from the tests' runs
C = {}
exec(open(CFG).read(), C)
if C.get("PRACTICAL"):  # relative to the workspace, like REPO (which flowmap.py hands over already joined)
    C["PRACTICAL"] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(CFG))), "..", C["PRACTICAL"])
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gitparts  # noqa: E402
import scan  # noqa: E402  (the static scan of a commit's code, shared with flowmap_playground's index)


def git0(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True, check=True).stdout


PART_META = {}
if "PARTS" in C:
    PARTS = C["PARTS"]
else:
    _ps, _upcoming, _base = gitparts.parts(REPO, C["WEEK_NUM"], C.get("PRACTICAL"))
    _all = ([_base] if _base else []) + _ps
    PARTS = [(p["commit"], p["label"], p["title"]) for p in _all]
    PART_META = {p["label"]: p for p in _all}
    C.setdefault("UPCOMING", _upcoming)
    C.setdefault("COMMIT", _ps[-1]["commit"])
    # the branch the week's code is on: main once main contains it (main may have moved on to a later week)
    _on = git0("branch", "--contains", C["COMMIT"], "--format=%(refname:short)").split()
    C.setdefault("BRANCH", "main" if "main" in _on else (_on[0] if _on else "detached"))
C.setdefault("EXPORT", f"exports/{PARTS[-1][0]}")
C.setdefault("CONDS_JSON", f"build/conds_{C['KEY']}.json")
CODE_DIRS = [d.strip("/") for d in C.get("CODE_DIRS", [])]  # Python outside src/ that is yours too: ["scripts"]
COMMITS = list(dict.fromkeys(commit for commit, _, _ in PARTS))
# a commit's code never changes, so what the map reads from it is kept (build/scan/): its files, its date, and its scan.
# A commit read for the first time costs one git call for all its code, not one per file
SCAN_DIR = "build/scan"
SCAN_STAMP = hashlib.md5(open(scan.__file__, "rb").read() + json.dumps([C.get("PKG"), CODE_DIRS]).encode()).hexdigest()[:10]


def kept(commit, what):
    try:
        return json.load(open(f"{SCAN_DIR}/{commit}_{SCAN_STAMP}.json"))[what]
    except (OSError, ValueError, KeyError):
        return None


def keep(commit, **values):
    path = f"{SCAN_DIR}/{commit}_{SCAN_STAMP}.json"
    try:
        saved = json.load(open(path))
    except (OSError, ValueError):
        saved = {}
    os.makedirs(SCAN_DIR, exist_ok=True)
    json.dump({**saved, **values}, open(path + ".tmp", "w"))
    os.replace(path + ".tmp", path)


def read_code(wanted):
    """{(commit, path): code} for every (commit, path) asked, in one git call."""
    if not wanted:
        return {}
    blobs = subprocess.run(["git", "-C", REPO, "cat-file", "--batch"], input="".join(f"{c}:{f}\n" for c, f in wanted).encode(),
                           capture_output=True, check=True).stdout
    text, at = {}, 0
    for key in wanted:  # "<sha> blob <size>\n<content>\n" each, in the order asked
        nl = blobs.index(b"\n", at)
        size = int(blobs[at:nl].split()[2])
        text[key] = blobs[nl + 1:nl + 1 + size].decode().replace("\r\n", "\n").replace("\r", "\n")  # as `git show` reads it
        at = nl + 2 + size
    return text


TREES = {}
for _c in COMMITS:
    TREES[_c] = kept(_c, "tree")
    if TREES[_c] is None:
        TREES[_c] = git0("ls-tree", "-r", "--name-only", _c).split()
        keep(_c, tree=TREES[_c])
_tree = TREES[PARTS[-1][0]]
PKG = C.get("PKG") or next(f.split("/")[1] for f in _tree if f.startswith("src/") and f.endswith("/__init__.py") and f.count("/") == 2)
LIBS = kept(PARTS[-1][0], "libs")
if LIBS is None:
    _src = [f for f in _tree if f.startswith(f"src/{PKG}/") and f.endswith(".py")]
    _text = read_code([(PARTS[-1][0], f) for f in _src])
    LIBS = sorted(scan.imported_libs([_text[(PARTS[-1][0], f)] for f in _src], PKG))
    keep(PARTS[-1][0], libs=LIBS)
LIBS = set(LIBS)
DATE = {c: kept(c, "date") for c in COMMITS}
if None in DATE.values():
    _dates = dict(line.split(" ", 1) for line in git0("log", "--no-walk=unsorted", "--format=%H %ad", "--date=format:%b %d %H:%M", *COMMITS).splitlines())
    for _c in COMMITS:
        DATE[_c] = next(d for full, d in _dates.items() if full.startswith(_c))
        keep(_c, date=DATE[_c])


def scan_commit(commit):
    """The map's scan of one commit (tools/scan.py), kept per commit and per library list."""
    libs = ",".join(sorted(LIBS))
    got = kept(commit, "scan")
    if got and got["libs"] == libs:
        return got["nodes"], {tuple(e) for e in got["edges"]}, {(a, b): (f, n) for a, b, f, n in got["lines"]}, got["moddoc"]
    files = scan.code_files(TREES[commit], PKG, CODE_DIRS)
    text = read_code([(commit, f) for f in files])
    nodes, edges, lines, moddoc = scan.scan({f: text[(commit, f)] for f in files}, PKG, LIBS)
    keep(commit, scan={"libs": libs, "nodes": nodes, "edges": sorted(edges), "lines": [[a, b, f, n] for (a, b), (f, n) in lines.items()], "moddoc": moddoc})
    return nodes, edges, lines, moddoc

# a word or two for the libraries a project uses; any other library is just "library"
LIB_DESC = {'httpx': 'HTTP library',
 'tenacity': 'Retry library',
 'asyncio': 'Async runtime',
 'numpy': 'Number arrays',
 'pydantic': 'Data checking',
 'fastapi': 'Web API library',
 'psycopg': 'Postgres driver',
 'sqlalchemy': 'Database library',
 'openai': 'OpenAI client',
 'anthropic': 'Anthropic client'}
DESC = {}  # one-line summaries for functions without a docstring come from the week's cfg (EXTRA_DESC)


# ---------------------------------------------------------------- static map per commit
MODDOC = {}  # each module's docstring (a later Part's wins)


def node_alias(nid):
    # moved or renamed code keeps one identity (W3 Part 1 moved error_for; W4 Part 2 renamed ChaosAPI to FlakyAPI)
    return C.get("ALIASES", {}).get(nid, nid)


parts = []
all_nodes = {}
prev = {}
prev_edges = set()
for commit, label, title in PARTS:
    nodes, edges, last_lines, moddoc = scan_commit(commit)
    MODDOC.update(moddoc)
    nodes = {node_alias(k): {**v, "home": k} for k, v in nodes.items()}
    edges = {(node_alias(a), node_alias(b), k) for a, b, k in edges}
    added = sorted(set(nodes) - set(prev))
    removed = sorted(set(prev) - set(nodes))
    changed = sorted(k for k in nodes if k in prev and nodes[k]["hash"] != prev[k]["hash"])
    moved = sorted(k for k in nodes if k in prev and nodes[k]["mod"] != prev[k]["mod"])
    parts.append({
        "commit": commit,
        "label": label,
        "title": title,
        "date": DATE[commit].strip(),
        "inProgress": bool(PART_META.get(label, {}).get("inProgress")),
        "nodes": sorted(nodes),
        "edges": sorted([list(e) for e in edges]),
        "added": added,
        "removed": removed,
        "changed": changed,
        "moved": moved,
        "tests": sorted(f[len("tests/"):] for f in TREES[commit] if f.startswith("tests/") and f.split("/")[-1].startswith("test_")),
    })
    for k, v in nodes.items():
        all_nodes.setdefault(k, {}).update(v)
        all_nodes[k].setdefault("since", label)
    prev, prev_edges = nodes, edges

final = parts[-1]
DESC.update(C.get("EXTRA_DESC", {}))
def short_doc(doc, words=6):
    w = doc.rstrip(".").split()
    return " ".join(w[:words]) + ("…" if len(w) > words else "")


for k in all_nodes:
    all_nodes[k]["desc"] = DESC.get(k) or short_doc(all_nodes[k].get("doc") or "")
    if k not in final["nodes"]:
        all_nodes[k]["gone"] = True
for lib in sorted(LIBS):
    all_nodes["lib." + lib] = {"kind": "lib", "mod": "lib", "desc": LIB_DESC.get(lib, "library"), "since": PARTS[0][1]}

# ---------------------------------------------------------------- runs
ADDR = re.compile(r" at 0x[0-9a-f]+")
RCS = re.compile(r"<RetryCallState \d+: attempt #(\d+); slept for ([\d.]+); last result: (failed|returned) \(?([^>]*?)\)?>")


def tidy(v):
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            out[k] = tidy(x)
        if out.get("t") == "RetryCallState" or (isinstance(out.get("v"), str) and out["v"].startswith("<RetryCallState")):
            m = RCS.search(v.get("v", ""))
            out = {"t": "RetryCallState", "lib": "tenacity", "v": f"attempt #{m.group(1)} failed" if m else "RetryCallState"}
        if out.get("t") == "wait_random_exponential":
            out["v"] = "wait_random_exponential(…)"
        if out.get("t") == "AsyncRetrying":
            out["v"] = "AsyncRetrying(stop=4 tries, wait=…, retry=is_transient)"
        if out.get("t") == "type" and isinstance(out.get("v"), str):
            out["v"] = out["v"].replace("<class '", "").replace("'>", "").split(".")[-1]
        if out.get("t") == "function" and isinstance(out.get("v"), str):
            out["v"] = out["v"].replace(".<locals>.", ".")
        return out
    if isinstance(v, list):
        return [tidy(x) for x in v]
    if isinstance(v, str):
        return ADDR.sub("", v)
    return v


def clean_run(path, meta):
    d = json.load(open(path))
    ev = [tidy(e) for e in d["events"]]
    for e in ev:
        if e.get("fn", "").endswith(".__init__"):
            e["fn"] = e["fn"][: -len(".__init__")]
        if e.get("fn"):
            e["fn"] = node_alias(e["fn"])
        if isinstance(e.get("coro"), dict) and e["coro"].get("fn"):
            e["coro"]["fn"] = node_alias(e["coro"]["fn"])
    # which frames finally unwound with which exception (to drop cleanup-only catches)
    unwound = {(e["id"], (e.get("exc") or {}).get("obj") or (e.get("exc") or {}).get("t")) for e in ev if e["k"] == "raise"}
    out = []
    seen_throw = set()
    seen_catch = set()
    i = 0
    while i < len(ev):
        e = ev[i]
        k = e["k"]
        if k in ("pause", "resume"):
            j = i
            while j < len(ev) and ev[j]["k"] == k and ev[j]["task"] == e["task"]:
                j += 1
            chain = ev[i:j]
            deepest = chain[0] if k == "pause" else chain[-1]
            out.append({"k": "wait" if k == "pause" else "wake", "id": deepest["id"], "fn": deepest["fn"], "task": e["task"], **({"at": deepest.get("at")} if k == "pause" else {})})
            i = j
            continue
        if k in ("throw", "catch"):
            key = (e["id"], e["exc"].get("obj") or e["exc"].get("t"))
            if k == "throw":
                exc_key = e["exc"].get("obj") or (e["exc"].get("t"), e["id"])
                if exc_key in seen_throw:
                    i += 1
                    continue
                seen_throw.add(exc_key)
            else:
                if key in unwound or key in seen_catch:
                    i += 1
                    continue
                seen_catch.add(key)
        if k == "call" and (e.get("via") or "").startswith("/"):
            e["via"] = None
        out.append(e)
        i += 1
    # in this mock every throw also needs to be first seen where it starts; drop throws in frames that only pass it on
    origin = {}
    final = []
    for e in out:
        if e["k"] == "throw":
            key = e["exc"].get("obj") or (e["exc"]["t"], e["id"])
            if key in origin:
                continue
            origin[key] = e["id"]
        final.append(e)
    for n, e in enumerate(final):
        e["i"] = n
        e.pop("t", None)
        if e["k"] == "born":
            e.pop("value", None)
    # chapters: calls made straight from the test (or its main)
    roots = {final[0]["id"]}
    for e in final:
        if e["k"] == "call" and e.get("parent") in roots and e["fn"].endswith(".<main>"):
            roots.add(e["id"])
    chapters = [{"i": e["i"], "fn": e["fn"], "args": e.get("args", [])[:1]} for e in final if e["k"] in ("call", "new") and e.get("parent") in roots and not e["fn"].endswith(".<main>")]
    objects = {k: {**v, "cls": node_alias(v["cls"].replace(".__init__", ""))} for k, v in d["objects"].items()}
    if meta.get("play"):  # a playground run: no test to read; what your code printed and its exit code instead
        return {**meta, "status": d["status"], "events": final, "objects": objects, "chapters": chapters, "tasks": d["tasks"], "endVars": [], "expects": [],
                **{k: d[k] for k in ("printed", "stderr", "exit", "returned") if k in d}}
    return {**meta, "status": d["status"], "events": final, "objects": objects, "chapters": chapters, "tasks": d["tasks"], "endVars": end_vars(meta, final), "expects": expects(meta)}


def end_vars(meta, events):
    if meta.get("end_fn"):
        ret = next(e for e in events if e["k"] == "return" and e["fn"] == meta["end_fn"])
        return [[meta["end_fn"].split(".")[-1] + "() ↩", ret["value"]]]
    # END = the values the test checks: every name used in its assert lines, with its value when the test finished
    src = open(f"{meta.get('export', C['EXPORT'])}/{meta['test']}").read()
    fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == meta["fn"])
    names = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Assert):
            for sub in ast.walk(node.test):
                if isinstance(sub, ast.Name) and sub.id not in names:
                    names.append(sub.id)
    root = events[0]["id"]
    ret = next(e for e in events if e["k"] == "return" and e["id"] == root)
    loc = dict(ret.get("locals") or [])
    out = [[n, loc[n]] for n in names if n in loc and loc[n].get("t") != "function"]
    main = next((e for e in events if e["k"] == "return" and e["fn"].endswith(".<main>")), None)
    if main and ("main" in names or not out):
        out.insert(0, ["main() ↩", main["value"]])
    if not out or (len(out) == 1 and out[0][1].get("t") == "None"):
        # e.g. assert two_requests(requests_per_minute=60) == [1.0169…]: END is what that helper returned
        helpers = {n.name for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and not n.name.startswith("test_")}
        test_mod = meta["test"].split("/")[-1][:-3]
        for node in ast.walk(fn):
            if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Call) \
                    and isinstance(node.test.left.func, ast.Name) and node.test.left.func.id in helpers:
                ret = next((e for e in events if e["k"] == "return" and e["fn"] == f"{test_mod}.{node.test.left.func.id}"), None)
                if ret:
                    return [[node.test.left.func.id + "() ↩", ret["value"]]]
    return out


def expects(meta):
    """What the test says should happen: its assert lines, as written."""
    src = open(f"{meta.get('export', C['EXPORT'])}/{meta['test']}").read()
    fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == meta["fn"])
    lines = [ast.unparse(n.test) for n in ast.walk(fn) if isinstance(n, ast.Assert)]
    return [x if len(x) <= 96 else x[:95] + "…" for x in lines[:6]]


RUN_META = list(C.get("RUN_META", []))
_have = {m["part"] for _, m in RUN_META}
for commit, label, title in PARTS:
    idx = f"{RUNS}/auto/{C['KEY']}/{label}/index.json"
    if label in _have or not os.path.exists(idx):
        continue
    saved = json.load(open(idx))
    if saved.get("commit") != commit:
        continue
    for n, pk in enumerate(saved["picked"]):
        RUN_META.append((pk["file"], {"key": f"auto_{label}_{n}", "part": label, "export": f"exports/{commit}", "title": pk["title"], "test": pk["test"], "fn": pk["fn"]}))
runs = [clean_run(f"{RUNS}/{f}", m) for f, m in RUN_META]
# your playground runs, listed in PLAY_DIR/index.json; they never feed the map's own guesses (fakes, checks, columns)
play = [clean_run(f"{PLAY_DIR}/{m['file']}", {**m, "play": True}) for m in json.load(open(f"{PLAY_DIR}/index.json"))] \
    if PLAY_DIR and os.path.exists(f"{PLAY_DIR}/index.json") else []
TEST_CODE = {e["fn"] for r in runs for e in r["events"] if e["k"] in ("call", "new") and ((e.get("def") or {}).get("file") or "").startswith("tests/")}


def is_test(fn):
    return fn in TEST_CODE or fn.split(".")[0].startswith("test_")


# a playground run's "you" frame (its driver's entry) is the test of that run: START is what it calls
for r in play:
    for e in r["events"]:
        if e["k"] == "call" and e["fn"].startswith("test_playground.") and e["fn"] not in all_nodes:
            all_nodes[e["fn"]] = {"kind": "test", "mod": "tests", "file": "tests/playground.py", "sig": "(text)", "since": PARTS[-1][1],
                                  "desc": "Your input", "label": e["fn"].split(".")[-1], "line": (e.get("def") or {}).get("line")}

# test-side nodes (entry points) and every edge the runs actually used
for r in runs:
    for e in r["events"]:
        if e["k"] in ("call", "new") and e["fn"] not in all_nodes:
            mod = e["fn"].split(".")[0]
            short = e["fn"].split(".", 1)[1]
            file = (e.get("def") or {}).get("file") or f"tests/{mod}.py"
            all_nodes[e["fn"]] = {
                "kind": "test" if is_test(e["fn"]) else "function",
                "mod": "tests",
                "file": file,
                "line": (e.get("def") or {}).get("line"),
                "sig": "()" if not e.get("args") else "(" + ", ".join(a[0] for a in e["args"]) + ")",
                "since": next((p["label"] for p in parts if file[len("tests/"):] in p["tests"]), PARTS[-1][1]),
                "desc": {"client_for": "Client wired to ChaosAPI", "main": "The async part of the test"}.get(short.split(".")[-1].strip("<>"), "Your test, the entry point"),
                "run": r["key"],
                "async": bool(e.get("async")),
                "label": short.split(".")[-1],
            }
# from Week 5 (and the production bridge) test code your code calls in the middle of a run shows, in its own column
# "from the test": a stand-in, a function the test hands in, a monkeypatched function. The test's own frames stay hidden
_week = C.get("WEEK_NUM")
FROM_TEST = isinstance(_week, str) or (_week or 0) >= 5
mid_parts = {}  # test function -> the Parts whose runs call it from your code
for r in runs if FROM_TEST else []:
    calls = {e["id"]: e for e in r["events"] if e["k"] in ("call", "new")}
    for e in calls.values():
        above = calls.get(e.get("parent"))
        while above and is_test(above["fn"]):
            above = calls.get(above.get("parent"))
        if is_test(e["fn"]) and above:
            mid_parts.setdefault(e["fn"], set()).add(r["part"])
for fn in mid_parts:
    all_nodes[fn].update(mid=True, desc="From the test")

run_edges = {}
for r in runs + play:  # play is empty unless this is the playground's build
    calls = {e["id"]: e for e in r["events"] if e["k"] in ("call", "new")}
    for e in calls.values():
        p = calls.get(e.get("parent"))
        if p:
            key = (p["fn"], e["fn"])
            rec = run_edges.setdefault(key, {"via": set(), "runs": set()})
            if e.get("via"):
                rec["via"].add(e["via"])
            rec["runs"].add(r["key"])
    for e in r["events"]:
        if e["k"] == "task":
            key = (calls[e["by"]]["fn"], e["coro"]["fn"])
            run_edges.setdefault(key, {"via": set(), "runs": set()})["via"].add("asyncio")
            run_edges[key]["runs"].add(r["key"])

def owner_class(fn):
    x = fn
    while x in all_nodes and all_nodes[x].get("kind") in ("method", "inner"):
        x = all_nodes[x].get("parent")
    return x if x in all_nodes and all_nodes[x].get("kind") == "class" else None


writes = {}
for r in runs:
    calls = {e["id"]: e for e in r["events"] if e["k"] in ("call", "new")}
    for e in r["events"]:
        if e["k"] != "set":
            continue
        c = calls.get(e["by"])
        cls = (r["objects"].get(e["obj"]) or {}).get("cls")
        if not c or not cls or is_test(c["fn"]) or c["fn"] == cls or owner_class(c["fn"]) == cls:
            continue
        rec = writes.setdefault((c["fn"], cls), {"fields": set(), "runs": set()})
        rec["fields"].add(e["field"])
        rec["runs"].add(r["key"])

LABELS = {
    "src/aiofetch/breaker.py:21": "if circuit open",
    "src/aiofetch/breaker.py:27": "on transient error",
    "src/aiofetch/breaker.py:29": "on permanent error",
    "src/aiofetch/breaker.py:33": "if probe fails",
    "src/aiofetch/breaker.py:35": "on success",
    "src/aiofetch/breaker.py:41": "if too many failures",
    "src/aiofetch/chaos.py:80": "if 200",
    "src/aiofetch/chaos.py:46": None,
    "src/aiofetch/client.py:55": "if rpm set",
    "src/aiofetch/client.py:79": "on timeout",
    "src/aiofetch/client.py:84": "if limiter",
    "src/aiofetch/client.py:105": "each try",
    "src/aiofetch/client.py:114": "per path",
    "src/aiofetch/client.py:125": "on error",
    "src/aiofetch/limiter.py:67": "until ready",
    "src/aiofetch/limiter.py:68": "until ready",
    "src/aiofetch/retry.py:22": "if HTTP error",
    "src/aiofetch/retry.py:46": "on error",
    "src/aiofetch/retry.py:51": "if no server hint",
    "src/aiofetch/transport.py:31": None,
    "src/aiofetch/transport.py:32": "if transient",
    "src/aiofetch/transport.py:33": "if transient",
    "src/aiofetch/transport.py:34": "else",
    "src/aiofetch/transport.py:42": "on HTTP error",
    "src/aiofetch/transport.py:44": "on timeout",
    "src/aiofetch/transport.py:46": "on network error",
    "src/aiofetch/retry.py:73": "if on_retry set",
}
LABELS = C.get("LINE_LABELS", LABELS if C["KEY"] == "W3" else {})
TEXT = {
    "if limiter is not None": "if limiter", "on HTTPStatusError": "on HTTP error", "on TimeoutException": "on timeout",
    "on TransportError": "on network error", "if answer == 200": "if 200", "if exc.transient": "on transient error",
    "if state != 'CLOSED'": "if circuit open", "if on_retry is not None": "if on_retry set", "on TimeoutError": "on timeout",
    "else of: requests_per_minute is None": "if rpm set", "on FetchError": "on error", "if params is None": None,
    "if rng is None": None, "if logger is None": None, "if headers is None": None,
}
def tidy_conds(raw, labels):
    out = {}
    for file, lines in raw.items():
        for line, cond in lines.items():
            key = f"{file}:{line}"
            if key in labels:
                cond = labels[key]
            elif cond in TEXT:
                cond = TEXT[cond]
            elif cond.startswith("in test:"):
                cond = None
            elif cond.startswith("else of:"):
                cond = "else"
            if cond:
                out.setdefault(file, {})[line] = cond if len(cond) <= 24 else cond[:23] + "…"
    for key, cond in labels.items():
        file, line = key.rsplit(":", 1)
        if cond and line not in out.get(file, {}):
            out.setdefault(file, {})[line] = cond
    return out


conds = tidy_conds(json.load(open(C["CONDS_JSON"])), LABELS)
conds_of = {}  # each code copy's conditions, worked out once however many runs use it (and kept with its commit's scan)
CONDS_STAMP = hashlib.md5(open("tools/conds.py", "rb").read() + json.dumps(CODE_DIRS).encode()).hexdigest()[:10]
for r in runs + play:
    exp = r.get("export")
    if exp and exp != C["EXPORT"]:
        if exp not in conds_of:
            commit, raw = exp.split("/")[-1], None
            got = kept(commit, "conds")
            if got and got["stamp"] == CONDS_STAMP:
                raw = got["raw"]
            else:
                tmp = f"build/.conds_{exp.replace('/', '_')}.json"
                subprocess.run([sys.executable, "tools/conds.py", exp, tmp, *CODE_DIRS], check=True, capture_output=True)
                raw = json.load(open(tmp))
                keep(commit, conds={"stamp": CONDS_STAMP, "raw": raw})
            conds_of[exp] = tidy_conds(raw, {})
        r["conds"] = conds_of[exp]
    r.pop("export", None)

# ---------------------------------------------------------------- the map's settings, worked out where missing
# a test fake: a class named like one (MockServer, FakeTransport, StubClock), or listed in the week's settings (FAKES)
FAKE_NAME = re.compile(r"(Mock|Fake|Stub|Dummy)[A-Z]")
auto_wiring = sorted(k for k in final["nodes"] if all_nodes[k]["kind"] == "class"
                     and (FAKE_NAME.match(k.split(".")[-1]) or k in C.get("FAKES", [])))
# a check: something the test only ever uses inside its assert lines to judge a result: a yes/no read with no arguments
# (r.ok) or a comparison (__eq__, __lt__, __contains__, __len__, __bool__; not __hash__ or __str__, which get tested). The call being tested inside an assert (assert ok.to_row() == {...}, assert
# save_lines(...) == 2) is your code's call, so it stays (the page uses the same rule)
asserted, plain = set(), set()
for r in runs:
    calls = {e["id"]: e for e in r["events"] if e["k"] in ("call", "new")}
    outs = {e["id"]: e for e in r["events"] if e["k"] in ("return", "raise", "born")}
    for e in calls.values():
        p = calls.get(e.get("parent"))
        if not p or not is_test(p["fn"]) or is_test(e["fn"]):
            continue
        on_assert = (e.get("site") or {}).get("text", "").lstrip().startswith("assert")
        o = outs.get(e["id"]) or {}
        yes_no = not [a for a in e.get("args", []) if a[0] != "self"] and (o.get("value") or {}).get("t") == "bool"
        dunder = bool(re.fullmatch(r"__(eq|ne|lt|le|gt|ge|contains|len|bool)__", e["fn"].split(".")[-1]))
        (asserted if on_assert and (yes_no or dunder) else plain).add(e["fn"])
auto_checks = sorted(fn for fn in asserted - plain if all_nodes.get(fn, {}).get("kind") in ("method", "inner"))
PALETTE = ["#7aa2f7", "#e8b464", "#ff9e64", "#c4a8ff", "#7dd3fc", "#9ece6a", "#2ac3de", "#bb9af7", "#e0af68", "#a9b1d6", "#f7768e"]
every = []
for prt in parts:
    for n in prt["nodes"]:
        if n not in every:
            every.append(n)
by_line = lambda n: (all_nodes[n]["mod"], all_nodes[n].get("line") or 0)  # noqa: E731
wiring_mods = {all_nodes[c]["mod"].split(".")[0] for c in auto_wiring}


def group(mod):
    """The column a module belongs to: itself, or its top-level subpackage (adapters.alpha -> adapters)."""
    return mod.split(".")[0]


def new_column(g, i):
    q = MODDOC.get(g, "").rstrip(".")
    q = q if len(q) <= 34 else q[:33].rsplit(" ", 1)[0] + "…"
    mods = {all_nodes[n]["mod"] for n in every if group(all_nodes[n]["mod"]) == g}
    return {"name": g.strip("_").replace("_", " "), "q": q, "file": f"{g}.py" if mods <= {g} else f"{g}/", "color": PALETTE[i % len(PALETTE)],
            "cards": sorted([n for n in every if group(all_nodes[n]["mod"]) == g], key=by_line)}


MAP = C.get("MAP")
if not MAP:
    # a project with no settings: one column per module, in the order a call from the tests reaches them, fakes last
    entry = {e["fn"] for r in runs for e in r["events"] if e["k"] in ("call", "new") and not is_test(e["fn"])
             and any(x["id"] == e.get("parent") and is_test(x["fn"]) for x in r["events"][: e["i"]] if x["k"] in ("call", "new"))}
    depth = {n: 0 for n in entry}
    frontier = list(entry)
    hops = [(a, b) for a, b, k in final["edges"] if k in ("call", "creates") and not b.startswith("lib.")]
    while frontier:
        nxt = []
        for a, b in hops:
            if a in frontier and b not in depth:
                depth[b] = depth[a] + 1
                nxt.append(b)
        frontier = nxt
    mods = sorted({group(all_nodes[n]["mod"]) for n in every} - {"__init__"})
    mod_depth = {m: min([depth[n] for n in every if group(all_nodes[n]["mod"]) == m and n in depth] or [99]) for m in mods}
    cols = [new_column(m, i) for i, m in enumerate(sorted(mods, key=lambda m: (m in wiring_mods, mod_depth[m], m)))]
    MAP = {"start": "your code", "end": "what comes back", "goal": C.get("GOAL", ""), "edges": [],
           "columns": [{"name": "START", "q": "your code calls in", "cards": ["@start"], "color": "#6fe0c5"}] + cols
           + [{"name": "END", "q": "what comes back", "cards": ["@end"], "color": "#6fe0c5"}]}
else:
    # a function the settings don't place goes to the column that holds most of its file, or to a new column for its file
    cols = MAP["columns"]
    placed = {x for col in cols for x in col["cards"]}
    for n in sorted(set(every) - placed - set(MAP.get("ignore", [])), key=by_line):
        mod = all_nodes[n]["mod"]
        counts = [(sum(1 for x in col["cards"] if all_nodes.get(x, {}).get("mod") == mod), i) for i, col in enumerate(cols)]
        best, i = max(counts)
        if best:
            cols[i]["cards"].append(n)
            continue
        fake_at = next((i for i, col in enumerate(cols) if any(x in auto_wiring for x in col["cards"])), len(cols) - 1)
        col = new_column(group(mod), len(cols))
        col["cards"] = [n]
        cols.insert(fake_at, col)
        print(f"map: new column for {col['file']}")
MAP["wiring"] = sorted(set(MAP.get("wiring", [])) | set(auto_wiring))
MAP["checks"] = sorted(set(MAP.get("checks", [])) | set(auto_checks))
if mid_parts:
    for prt in parts:
        prt["nodes"] = sorted(set(prt["nodes"]) | {fn for fn, labels in mid_parts.items() if prt["label"] in labels})
    end = next((i for i, col in enumerate(MAP["columns"]) if "@end" in col["cards"]), len(MAP["columns"]))
    MAP["columns"].insert(end, {"name": "from the test", "q": "the test's stand-ins", "file": "tests/",
                                "color": PALETTE[end % len(PALETTE)], "cards": sorted(mid_parts)})
first_run = next((r for r in runs if r["part"] == PARTS[-1][1]), None)
CORE = C.get("CORE") or sorted({e["fn"] for e in (first_run or {"events": []})["events"] if e["k"] in ("call", "new") and not is_test(e["fn"])})

data = {
    "key": C["KEY"], "name": C["NAME"], "week": C["WEEK"], "branch": C["BRANCH"], "commit": C["COMMIT"],
    "upcoming": C.get("UPCOMING", []), "core": CORE,
    "repo": {"name": C["NAME"], "week": C["WEEK"], "branch": C["BRANCH"], "commit": C["COMMIT"]},
    "conds": conds,
    "edgeLines": {f"{node_alias(a)}|{node_alias(b)}": list(v) for (a, b), v in last_lines.items()},
    "nodes": all_nodes,
    "parts": parts,
    "runEdges": [[a, b, sorted(v["via"]), sorted(v["runs"])] for (a, b), v in sorted(run_edges.items())],
    "writes": [[a, b, sorted(v["fields"]), sorted(v["runs"])] for (a, b), v in sorted(writes.items())],
    "map": MAP,
    "runs": runs,
    **({"play": play} if PLAY_DIR else {}),
}
if MAP:
    placed = [x for col in MAP["columns"] for x in col["cards"]]
    dup = sorted({x for x in placed if placed.count(x) > 1})
    every = {n for prt in parts for n in prt["nodes"]} - set(MAP.get("ignore", []))
    print("map: placed", len(placed), "| not placed (any part):", sorted(every - set(placed)), "| twice:", dup, "| fakes:", MAP["wiring"], "| assert-only:", MAP["checks"])
open(OUT, "w").write(json.dumps(data, separators=(",", ":"), default=list))
js = json.dumps(data)
print("nodes", len(all_nodes), "| parts", [(p["label"], len(p["nodes"]), len(p["edges"]), len(p["added"]), len(p["changed"])) for p in parts])
print("run events", [(r["key"], len(r["events"]), r["status"]) for r in runs], "| bytes", len(js))
missing = [k for k, v in all_nodes.items() if not v.get("desc")]
print("no desc:", missing)
