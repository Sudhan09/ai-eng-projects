"""The map's static scan of one commit's code: its functions, classes and methods, and which calls which.

Used by build_project.py (the map) and by flowmap_playground's index (which code reaches a function, and where).
It reads the code it is given, so it never runs git itself: build_project.py reads every file of a commit in one go.
"""

import ast
import hashlib
import sys

LIB_ALIASES = {"np": "numpy"}


def mod_key(f, pkg):
    """A file's module as the map (and the recorder) names it: batch, adapters.alpha, scripts.seed."""
    if f.startswith(f"src/{pkg}/"):
        rel = f[len(f"src/{pkg}/"):-3].replace("/", ".")
        return rel[: -len(".__init__")] if rel.endswith(".__init__") else rel
    return f[:-3].replace("/", ".")


def code_files(paths, pkg, code_dirs=()):
    """The files of yours a scan reads: the package, and Python outside src/ the settings name (CODE_DIRS)."""
    return [f for f in paths if f.endswith(".py") and (f.startswith(f"src/{pkg}/") or any(f.startswith(d + "/") for d in code_dirs))]


def imported_libs(texts, pkg):
    """Third-party packages the code imports (plus asyncio, whose calls the map shows as "tasks"). `texts`: the package's
    files' code."""
    found = set()
    for text in texts:
        for n in ast.walk(ast.parse(text)):
            names = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module] if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module else []
            found |= {x.split(".")[0] for x in names}
    return {x for x in found if x != pkg and (x == "asyncio" or x not in sys.stdlib_module_names)}


def scan(files, pkg, libs, sites=None):
    """files: {path: code} of one commit (code_files order). Returns (nodes, edges, edge_lines, moddoc). When `sites` is
    a dict, every call's place is added to it: (caller, callee) -> [(file, line, col)]."""
    sources = {mod_key(f, pkg): text for f, text in files.items()}
    file_of = {mod_key(f, pkg): f for f in files}
    package_of = {m: m if file_of[m].endswith("/__init__.py") and m != "__init__" else m.rpartition(".")[0] for m in sources}
    moddoc = {}

    def from_mod(mod, n):
        """The project module an import names (from .record, from ..core, from logparse.record), or None."""
        if n.level:
            base = package_of[mod].split(".") if package_of[mod] else []
            base = base[: len(base) - (n.level - 1)] if n.level > 1 else base
            return ".".join(base + ([n.module] if n.module else []))
        if n.module == pkg or (n.module or "").startswith(pkg + "."):
            return n.module[len(pkg) + 1:]
        return None

    def name_in(m, name):
        return f"{m}.{name}" if m else name
    nodes, edges = {}, set()
    edge_lines = {}  # (caller, callee) -> (file, first line of the call)
    imports = {}  # mod -> {local name: target node id or lib}
    classes = {}  # mod -> {class name: ClassDef}
    trees = {mod: ast.parse(src) for mod, src in sources.items()}
    for mod, src in sources.items():
        tree = trees[mod]
        imp = {}
        for n in tree.body:
            if isinstance(n, ast.ImportFrom):
                m = from_mod(mod, n)
                if m is not None:
                    for a in n.names:
                        imp[a.asname or a.name] = name_in(m, a.name)  # a function, a class, or a submodule
                elif n.module and n.module.split(".")[0] in libs:
                    for a in n.names:
                        imp[a.asname or a.name] = "lib." + n.module.split(".")[0]
            elif isinstance(n, ast.Import):
                for a in n.names:
                    root = a.name.split(".")[0]
                    if root in libs:
                        imp[a.asname or a.name] = "lib." + root
                    elif a.name.startswith(pkg + ".") and a.asname:  # import logparse.record as rec
                        imp[a.asname] = a.name[len(pkg) + 1:]
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                imp[n.name] = f"{mod}.{n.name}"
        imports[mod] = imp
        classes[mod] = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
        moddoc[mod] = ((ast.get_docstring(tree) or "").strip().splitlines() or [""])[0]

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
                elif root in libs:
                    hits.append(("lib", "lib." + root))
                elif v.id in imp:
                    hits.append(("call", f"{imp[v.id]}.{f.attr}"))
            elif isinstance(v, ast.Attribute):
                base = v
                while isinstance(base, ast.Attribute):
                    base = base.value
                if isinstance(base, ast.Name) and LIB_ALIASES.get(base.id, base.id) in libs:
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
        # which function each piece of code is in: the last local def (in walk order) that holds it, found once
        owner_of = {}
        for name, inner_id in local_defs.items():
            inner = next(x for x in ast.walk(fn) if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == name)
            for x in ast.walk(inner):
                owner_of[id(x)] = inner_id
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Call):
                owner = owner_of.get(id(sub), fn_id)
                for kind, target in resolve(mod, owner_cls, owner, sub, local_defs):
                    edges.add((owner, target, kind))
                    edge_lines.setdefault((owner, target), (file_of[mod], sub.lineno))
                    if sites is not None:
                        sites.setdefault((owner, target), []).append((file_of[mod], sub.lineno, sub.col_offset))
        # errors it catches: an except clause that names one of the project's own classes
        for sub in ast.walk(fn):
            if isinstance(sub, ast.ExceptHandler) and sub.type is not None:
                owner = owner_of.get(id(sub), fn_id)
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
        tree = trees[mod]
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
    return nodes, clean, edge_lines, moddoc


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
