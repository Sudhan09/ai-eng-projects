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
C = {}
exec(open(CFG).read(), C)
if C.get("PRACTICAL"):  # relative to the workspace, like REPO (which flowmap.py hands over already joined)
    C["PRACTICAL"] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(CFG))), "..", C["PRACTICAL"])
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gitparts  # noqa: E402


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
_tree = git0("ls-tree", "-r", "--name-only", PARTS[-1][0]).split()
PKG = C.get("PKG") or next(f.split("/")[1] for f in _tree if f.startswith("src/") and f.endswith("/__init__.py") and f.count("/") == 2)
def imported_libs(commit):
    """Third-party packages the code imports (plus asyncio, whose calls the map shows as "tasks")."""
    found = set()
    for f in _tree:
        if f.startswith(f"src/{PKG}/") and f.endswith(".py"):
            for n in ast.walk(ast.parse(git0("show", f"{commit}:{f}"))):
                names = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module] if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module else []
                found |= {x.split(".")[0] for x in names}
    return {x for x in found if x != PKG and (x == "asyncio" or x not in sys.stdlib_module_names)}


LIBS = imported_libs(PARTS[-1][0])
LIB_ALIASES = {"np": "numpy"}

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


def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True, check=True).stdout


# ---------------------------------------------------------------- static map per commit
MODDOC = {}  # of the commit scanned last: each module's docstring


CODE_DIRS = [d.strip("/") for d in C.get("CODE_DIRS", [])]  # Python outside src/ that is yours too: ["scripts"]


def mod_key(f):
    """A file's module as the map (and the recorder) names it: batch, adapters.alpha, scripts.seed."""
    if f.startswith(f"src/{PKG}/"):
        rel = f[len(f"src/{PKG}/"):-3].replace("/", ".")
        return rel[: -len(".__init__")] if rel.endswith(".__init__") else rel
    return f[:-3].replace("/", ".")


def scan(commit):
    files = [f for f in git("ls-tree", "-r", "--name-only", commit).split() if f.endswith(".py")
             and (f.startswith(f"src/{PKG}/") or any(f.startswith(d + "/") for d in CODE_DIRS))]
    sources = {mod_key(f): git("show", f"{commit}:{f}") for f in files}
    file_of = {mod_key(f): f for f in files}
    package_of = {m: m if file_of[m].endswith("/__init__.py") and m != "__init__" else m.rpartition(".")[0] for m in sources}

    def from_mod(mod, n):
        """The project module an import names (from .record, from ..core, from logparse.record), or None."""
        if n.level:
            base = package_of[mod].split(".") if package_of[mod] else []
            base = base[: len(base) - (n.level - 1)] if n.level > 1 else base
            return ".".join(base + ([n.module] if n.module else []))
        if n.module == PKG or (n.module or "").startswith(PKG + "."):
            return n.module[len(PKG) + 1:]
        return None

    def name_in(m, name):
        return f"{m}.{name}" if m else name
    nodes, edges = {}, set()
    edge_lines = {}  # (caller, callee) -> (file, first line of the call)
    imports = {}  # mod -> {local name: target node id or lib}
    classes = {}  # mod -> {class name: ClassDef}
    for mod, src in sources.items():
        tree = ast.parse(src)
        imp = {}
        for n in tree.body:
            if isinstance(n, ast.ImportFrom):
                m = from_mod(mod, n)
                if m is not None:
                    for a in n.names:
                        imp[a.asname or a.name] = name_in(m, a.name)  # a function, a class, or a submodule
                elif n.module and n.module.split(".")[0] in LIBS:
                    for a in n.names:
                        imp[a.asname or a.name] = "lib." + n.module.split(".")[0]
            elif isinstance(n, ast.Import):
                for a in n.names:
                    root = a.name.split(".")[0]
                    if root in LIBS:
                        imp[a.asname or a.name] = "lib." + root
                    elif a.name.startswith(PKG + ".") and a.asname:  # import logparse.record as rec
                        imp[a.asname] = a.name[len(PKG) + 1:]
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                imp[n.name] = f"{mod}.{n.name}"
        imports[mod] = imp
        classes[mod] = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
        MODDOC[mod] = ((ast.get_docstring(tree) or "").strip().splitlines() or [""])[0]

    def add_node(nid, kind, node, mod, parent=None, src=None):
        seg = ast.get_source_segment(src, node) or ""
        nodes[nid] = {
            "kind": kind,
            "mod": mod,
            "file": file_of[mod],
            "line": node.lineno,
            "parent": parent,
            "async": isinstance(node, ast.AsyncFunctionDef),
            "sig": signature(node) if not isinstance(node, ast.ClassDef) else bases(node),
            "hash": hashlib.md5(seg.encode()).hexdigest()[:8],
            "doc": ((ast.get_docstring(node) or "").strip().splitlines() or [""])[0],
        }

    def attr_types(cls):
        out = {}
        for item in cls.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for st in ast.walk(item):
                    if isinstance(st, ast.Assign) and isinstance(st.value, ast.Call):
                        for tgt in st.targets:
                            if isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name) and tgt.value.id == "self":
                                f = st.value.func
                                if isinstance(f, ast.Name):
                                    out[tgt.attr] = f.id
                                elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                                    out[tgt.attr] = f.value.id
        return out

    def resolve(mod, owner_cls, fn_id, call, local_defs):
        f = call.func
        imp = imports[mod]
        hits = []
        if isinstance(f, ast.Name):
            if f.id in local_defs:
                hits.append(("call", local_defs[f.id]))
            elif f.id in imp:
                hits.append(("call", imp[f.id]))
            elif f.id == "cls" and owner_cls:
                hits.append(("call", f"{mod}.{owner_cls.name}"))
        elif isinstance(f, ast.Attribute):
            v = f.value
            if isinstance(v, ast.Name) and v.id == "self" and owner_cls:
                hits.append(("call", f"{mod}.{owner_cls.name}.{f.attr}"))
            elif isinstance(v, ast.Attribute) and isinstance(v.value, ast.Name) and v.value.id == "self" and owner_cls:
                t = attr_types(owner_cls).get(v.attr)
                if t and t in imp:
                    hits.append(("call", f"{imp[t]}.{f.attr}"))
                elif t and t in classes[mod]:
                    hits.append(("call", f"{mod}.{t}.{f.attr}"))
            elif isinstance(v, ast.Name):
                root = LIB_ALIASES.get(v.id, v.id)
                if v.id in imp and imp[v.id].startswith("lib."):
                    hits.append(("lib", imp[v.id]))
                elif root in LIBS:
                    hits.append(("lib", "lib." + root))
                elif v.id in imp:
                    hits.append(("call", f"{imp[v.id]}.{f.attr}"))
            elif isinstance(v, ast.Attribute):
                base = v
                while isinstance(base, ast.Attribute):
                    base = base.value
                if isinstance(base, ast.Name) and LIB_ALIASES.get(base.id, base.id) in LIBS:
                    hits.append(("lib", "lib." + LIB_ALIASES.get(base.id, base.id)))
        # functions handed over to be called later (callbacks)
        for a in [*call.args, *[k.value for k in call.keywords]]:
            if isinstance(a, ast.Name) and (a.id in local_defs or (a.id in imp and not imp[a.id].startswith("lib."))):
                hits.append(("passes", local_defs.get(a.id) or imp[a.id]))
            if isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name) and a.value.id == "self" and owner_cls:
                hits.append(("passes", f"{mod}.{owner_cls.name}.{a.attr}"))
        return hits

    def walk_fn(mod, src, fn, fn_id, owner_cls):
        local_defs = {}
        for sub in ast.walk(fn):
            if sub is not fn and isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                local_defs[sub.name] = f"{fn_id}.<{sub.name}>"
                add_node(local_defs[sub.name], "inner", sub, mod, parent=fn_id, src=src)
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Call):
                owner = fn_id
                for name, inner_id in local_defs.items():
                    inner = next(x for x in ast.walk(fn) if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == name)
                    if sub in list(ast.walk(inner)):
                        owner = inner_id
                for kind, target in resolve(mod, owner_cls, owner, sub, local_defs):
                    edges.add((owner, target, kind))
                    edge_lines.setdefault((owner, target), (file_of[mod], sub.lineno))
        # errors it catches: an except clause that names one of the project's own classes
        for sub in ast.walk(fn):
            if isinstance(sub, ast.ExceptHandler) and sub.type is not None:
                owner = fn_id
                for name, inner_id in local_defs.items():
                    inner = next(x for x in ast.walk(fn) if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == name)
                    if sub in list(ast.walk(inner)):
                        owner = inner_id
                for t in sub.type.elts if isinstance(sub.type, ast.Tuple) else [sub.type]:
                    target = imports[mod].get(t.id) if isinstance(t, ast.Name) else None
                    if target and not target.startswith("lib."):
                        edges.add((target, owner, "catches"))
                        edge_lines.setdefault((target, owner), (file_of[mod], sub.lineno))

    # a starter stub (raise NotImplementedError, with a "# TODO" or a "Stage 1" message or nothing) is not built yet:
    # it joins the map in the Part that fills it in. An abstract method (@abstractmethod, or on an ABC or Protocol) stays
    def is_stub(fn, cls=None):
        body = [b for b in fn.body if not (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant) and isinstance(b.value.value, str))]
        if len(body) != 1 or not isinstance(body[0], ast.Raise) or body[0].exc is None:
            return False
        exc = body[0].exc.func if isinstance(body[0].exc, ast.Call) else body[0].exc
        if not (isinstance(exc, ast.Name) and exc.id == "NotImplementedError"):
            return False
        last = lambda x: ast.unparse(x).split(".")[-1]  # noqa: E731
        abstract = any(last(d) == "abstractmethod" for d in fn.decorator_list) or (cls is not None and (
            any(last(b) in ("ABC", "Protocol") for b in cls.bases) or any(k.arg == "metaclass" and last(k.value) == "ABCMeta" for k in cls.keywords)))
        return not abstract

    for mod, src in sources.items():
        tree = ast.parse(src)
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if is_stub(n):
                    continue
                nid = f"{mod}.{n.name}"
                add_node(nid, "function", n, mod, src=src)
                walk_fn(mod, src, n, nid, None)
            elif isinstance(n, ast.ClassDef):
                cid = f"{mod}.{n.name}"
                add_node(cid, "class", n, mod, src=src)
                for b in n.bases:
                    if isinstance(b, ast.Name) and (b.id in imports[mod] or b.id in classes[mod]):
                        target = imports[mod].get(b.id) or f"{mod}.{b.id}"
                        if not target.startswith("lib."):
                            edges.add((cid, target, "inherits"))
                for item in n.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        mid = f"{cid}.{item.name}"
                        if item.name == "__init__":
                            walk_fn(mod, src, item, cid, n)  # creating the object is the class's own work
                            continue
                        if is_stub(item, n):
                            continue
                        add_node(mid, "method", item, mod, parent=cid, src=src)
                        walk_fn(mod, src, item, mid, n)
    # moved functions keep their identity (Part A had error_for in errors.py)
    known = set(nodes)
    clean = set()
    for a, b, k in edges:
        if a == b:
            continue
        if b.startswith("lib."):
            clean.add((a, b, "lib"))
        elif k == "catches":
            if a in known:
                clean.add((a, b, k))
        elif b in known:
            if nodes[b]["kind"] == "class":
                if k == "passes":
                    continue  # isinstance(exc, FetchError): a check, not a hand-off
                if k == "call":
                    k = "creates"
            clean.add((a, b, k))
    return nodes, clean, edge_lines


def signature(fn):
    a = fn.args
    parts = []
    pos = a.posonlyargs + a.args
    defaults = [None] * (len(pos) - len(a.defaults)) + list(a.defaults)
    for arg, d in zip(pos, defaults):
        if arg.arg in ("self", "cls"):
            continue
        parts.append(arg.arg + ("=" + ast.unparse(d) if d is not None else ""))
    if a.vararg:
        parts.append("*" + a.vararg.arg)
    elif a.kwonlyargs:
        parts.append("*")
    for arg, d in zip(a.kwonlyargs, a.kw_defaults):
        parts.append(arg.arg + ("=" + ast.unparse(d) if d is not None else ""))
    if a.kwarg:
        parts.append("**" + a.kwarg.arg)
    return "(" + ", ".join(parts) + ")"


def bases(cls):
    names = [ast.unparse(b) for b in cls.bases]
    deco = [ast.unparse(d) for d in cls.decorator_list]
    return {"bases": names, "deco": deco}


def node_alias(nid):
    # moved or renamed code keeps one identity (W3 Part 1 moved error_for; W4 Part 2 renamed ChaosAPI to FlakyAPI)
    return C.get("ALIASES", {}).get(nid, nid)


parts = []
all_nodes = {}
prev = {}
prev_edges = set()
for commit, label, title in PARTS:
    nodes, edges, last_lines = scan(commit)
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
        "date": git("log", "-1", "--format=%ad", "--date=format:%b %d %H:%M", commit).strip(),
        "inProgress": bool(PART_META.get(label, {}).get("inProgress")),
        "nodes": sorted(nodes),
        "edges": sorted([list(e) for e in edges]),
        "added": added,
        "removed": removed,
        "changed": changed,
        "moved": moved,
        "tests": sorted(f[len("tests/"):] for f in git("ls-tree", "-r", "--name-only", commit).split() if f.startswith("tests/") and f.split("/")[-1].startswith("test_")),
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
TEST_CODE = {e["fn"] for r in runs for e in r["events"] if e["k"] in ("call", "new") and ((e.get("def") or {}).get("file") or "").startswith("tests/")}


def is_test(fn):
    return fn in TEST_CODE or fn.split(".")[0].startswith("test_")


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
for r in runs:
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
for r in runs:
    exp = r.get("export")
    if exp and exp != C["EXPORT"]:
        tmp = f"build/.conds_{exp.replace('/', '_')}.json"
        subprocess.run([sys.executable, "tools/conds.py", exp, tmp, *CODE_DIRS], check=True, capture_output=True)
        r["conds"] = tidy_conds(json.load(open(tmp)), {})
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
    return {"name": g.replace("_", " "), "q": q, "file": f"{g}.py" if mods <= {g} else f"{g}/", "color": PALETTE[i % len(PALETTE)],
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
