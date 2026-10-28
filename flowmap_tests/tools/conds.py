"""For every call in a project export (its package under src/ and its tests), the condition it runs under
(if / except / else / loop)."""
import ast, json, os, sys

ROOT = sys.argv[1]  # the w3 export


def short(src):
    return src.replace("self.", "")


def conds_for(path):
    src = open(path).read()
    tree = ast.parse(src)
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        cur, cond = node, None
        while cur in parents:
            par = parents[cur]
            if isinstance(par, ast.ExceptHandler):
                cond = "on " + (ast.unparse(par.type).split(".")[-1] if par.type else "error")
                break
            if isinstance(par, ast.If):
                test = short(ast.unparse(par.test))
                if any(cur is s for s in par.body):
                    cond = "if " + test
                elif any(cur is s for s in par.orelse):
                    cond = "else of: " + test
                else:
                    cond = "in test: " + test
                break
            if isinstance(par, ast.Try) and any(cur is s for s in par.finalbody):
                cond = "finally"
                break
            if isinstance(par, (ast.For, ast.AsyncFor, ast.While)) and any(cur is s for s in par.body):
                cond = "in loop"
                break
            if isinstance(par, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                break
            cur = par
        if cond:
            out.setdefault(node.lineno, cond)
    return out


res = {}
# the package is the one folder under src/ with an __init__.py (src/aiofetch, src/logparse, ...)
pkg = next(d for d in sorted(os.listdir(os.path.join(ROOT, "src"))) if os.path.exists(os.path.join(ROOT, "src", d, "__init__.py")))
for sub in (f"src/{pkg}", "tests", *[d for d in sys.argv[3:]]):  # extra code folders (scripts) after the output
    for d, subs, files in os.walk(os.path.join(ROOT, sub)):  # subpackages and test subfolders too
        subs[:] = sorted(x for x in subs if x != "__pycache__")
        for f in sorted(files):
            if f.endswith(".py"):
                rel = os.path.relpath(os.path.join(d, f), ROOT)
                c = conds_for(os.path.join(ROOT, rel))
                if c:
                    res[rel] = c
json.dump(res, open(sys.argv[2], "w"), indent=1)
for rel, c in res.items():
    if rel.startswith("src") or "part5" in rel:
        for line, cond in sorted(c.items()):
            print(f"{rel}:{line}  {cond}")
