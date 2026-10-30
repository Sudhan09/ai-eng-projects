"""What the playground knows about one commit's code without running it, read once per commit and kept in memory.

- The call graph, from the map's own scan (flowmap_tests/tools/scan.py): calls[fn] and callers[fn], and where each
  call is (file, line, column).
- Where a value comes from (Shrink): a loop's count is traced back name by name (backward slicing), through the
  function and the calls into it, to a number in your code (a parameter's default, a module constant, a value in the
  loop itself, an argparse default) or to something outside it (your input, a file).
- Where such a value is, in any commit, so a change can be made in the run's own copy of the code (patches).

Names are the map's: "lab.load", "client.AiofetchClient.get_item", "lab.load.<one>" (a function inside a function).
"""

import ast
import os

import scan  # flowmap_tests/tools (on the path through server.py)

PASS_THROUGH = {"range", "len", "list", "tuple", "sorted", "reversed", "enumerate", "zip", "set", "frozenset", "min", "max",
                "int", "abs", "iter", "islice"}
LOOPS = (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
DEFS = (ast.FunctionDef, ast.AsyncFunctionDef)


def literal(node):
    """A value written straight into the code: a number, text, True/False/None, or a list/tuple/set/dict of them."""
    try:
        ast.literal_eval(node)
        return True
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return False


class Index:
    def __init__(self, export):
        self.export = export
        src = os.path.join(export, "src")
        self.pkg = next(d for d in sorted(os.listdir(src)) if os.path.isfile(os.path.join(src, d, "__init__.py")))
        paths = []
        for d, subs, files in os.walk(os.path.join(src, self.pkg)):
            subs[:] = sorted(s for s in subs if s != "__pycache__")
            paths += [os.path.relpath(os.path.join(d, f), export).replace(os.sep, "/") for f in files]
        files = scan.code_files(sorted(paths), self.pkg)
        self.text = {f: open(os.path.join(export, f), encoding="utf-8").read() for f in files}
        self.libs = scan.imported_libs(list(self.text.values()), self.pkg)
        self.sites = {}
        self.nodes, edges, _, _ = scan.scan(self.text, self.pkg, self.libs, sites=self.sites)
        self.calls, self.callers = {}, {}
        for a, b, kind in edges:
            if kind in ("call", "creates"):
                self.calls.setdefault(a, set()).add(b)
                self.callers.setdefault(b, set()).add(a)
        self.trees = {f: ast.parse(t) for f, t in self.text.items()}
        self._pos = {}  # file -> {(line, col): Call}
        self._parent = {}  # file -> {id(node): parent node}
        self.defs = {}  # map name -> (file, def or class node, its class node or None)
        self.mods = {}  # module -> file
        self.consts = {}  # module -> {NAME: the value it is given at the top of the module}
        self.imported = {}  # module -> {local name: (module, name)} for `from .x import NAME`
        for f, tree in self.trees.items():
            mod = scan.mod_key(f, self.pkg)
            self.mods[mod] = f
            self.consts[mod], self.imported[mod] = {}, {}
            for n in [*tree.body, *(x for b in tree.body if isinstance(b, (ast.If, ast.Try)) for x in b.body)]:  # `if TYPE_CHECKING:` imports too
                if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                    self.consts[mod][n.targets[0].id] = n.value
                elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.value is not None:
                    self.consts[mod][n.target.id] = n.value
                elif isinstance(n, ast.ImportFrom):
                    target = self._from_mod(mod, f, n)
                    for a in n.names if target is not None else ():
                        self.imported[mod][a.asname or a.name] = (target, a.name)
            self._add_defs(f, mod, tree.body, None, None)

    def _from_mod(self, mod, f, n):
        if n.level:
            base = mod.split(".") if f.endswith("/__init__.py") else mod.split(".")[:-1]
            base = base[: len(base) - (n.level - 1)] if n.level > 1 else base
            return ".".join(base + ([n.module] if n.module else []))
        if n.module and (n.module == self.pkg or n.module.startswith(self.pkg + ".")):
            return n.module[len(self.pkg) + 1:]
        return None

    def _add_defs(self, f, prefix, body, cls, inside):
        for n in body:
            if isinstance(n, DEFS):
                name = f"{prefix}.<{n.name}>" if inside else f"{prefix}.{n.name}"
                self.defs[name] = (f, n, cls)
                self._add_inner(f, name, n)
            elif isinstance(n, ast.ClassDef) and not inside:
                name = f"{prefix}.{n.name}"
                self.defs[name] = (f, n, None)
                self._add_defs(f, name, n.body, n, None)

    def _add_inner(self, f, name, fn):
        """Functions written inside a function, named as the recorder names them (lab.load.<one>)."""
        for n in ast.walk(fn):
            if n is not fn and isinstance(n, DEFS) and self.def_of(f, n) is fn:
                inner = f"{name}.<{n.name}>"
                self.defs[inner] = (f, n, None)
                self._add_inner(f, inner, n)

    def def_of(self, f, node):
        """The function a piece of code is written in."""
        up = self.parent(f, node)
        while up is not None and not isinstance(up, (*DEFS, ast.Lambda)):
            up = self.parent(f, up)
        return up

    def parent(self, f, node):
        if f not in self._parent:
            self._parent[f] = {id(c): p for p in ast.walk(self.trees[f]) for c in ast.iter_child_nodes(p)}
        return self._parent[f].get(id(node))

    # ------------------------------------------------------------ functions
    def params(self, fn):
        """[(name, default node or None)] of a function, or of a class (its __init__), without self/cls."""
        f, node, _ = self.defs.get(fn, (None, None, None))
        if isinstance(node, ast.ClassDef):
            if self.enum(fn):
                return [("value", None)]
            owner = self.init_of(fn)
            init = self.defs[owner][1] if owner else None
            if init is None:  # a dataclass or a pydantic model: its fields (Field(min_length=1) has no default)
                return [(n.target.id, None if self.required(n.value) else n.value) for n in node.body
                        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and "ClassVar" not in ast.unparse(n.annotation)]
            node = init
        if not isinstance(node, DEFS):
            return []
        a = node.args
        pos = a.posonlyargs + a.args
        out = list(zip([x.arg for x in pos], [None] * (len(pos) - len(a.defaults)) + list(a.defaults)))
        out += [(x.arg, d) for x, d in zip(a.kwonlyargs, a.kw_defaults)]
        return [(n, d) for n, d in out if n not in ("self", "cls")]

    def bases(self, cls):
        """A class's own classes of yours it builds on, nearest first (its MRO, as far as your code goes)."""
        out, todo = [], [cls]
        while todo:
            c = todo.pop(0)
            node = self.defs.get(c, (None, None))[1]
            if isinstance(node, ast.ClassDef) and c not in out:
                out.append(c)
                todo += [t for b in node.bases if (t := self.type_of(b, c)) and t != "plain"]
        return out

    def init_of(self, cls):
        """The __init__ of yours that makes a class: its own, or the nearest class of yours it builds on has. None when
        it has none (a dataclass's is written by Python; a pydantic model's or an exception's is the library's)."""
        return next((f"{c}.__init__" for c in self.bases(cls) if f"{c}.__init__" in self.defs), None)

    def enum(self, cls):
        node = self.defs[cls][1]
        return any(ast.unparse(b).split(".")[-1] in ("Enum", "IntEnum", "StrEnum", "Flag", "IntFlag") for b in node.bases)

    def members(self, cls):
        """An enum's members, in order (LogLevel: DEBUG, INFO, ...)."""
        return [t.id for n in self.defs[cls][1].body if isinstance(n, ast.Assign) for t in n.targets
                if isinstance(t, ast.Name) and not t.id.startswith("_")]

    def dataclass(self, cls):
        node = self.defs[cls][1]
        return any(ast.unparse(d).split("(")[0].split(".")[-1] == "dataclass" for d in node.decorator_list)

    def runs_code(self, cls):
        """Whether making an object of this class runs code the recorder sees: an __init__ of yours, or a dataclass's."""
        return self.init_of(cls) is not None or any(self.dataclass(c) for c in self.bases(cls))

    @staticmethod
    def required(value):
        """A field with no default: none written, or Field(...)/field(...) without default= (or with ... first)."""
        if value is None:
            return True
        if isinstance(value, ast.Call) and ast.unparse(value.func).split(".")[-1] in ("Field", "field"):
            first = value.args[0] if value.args else None
            given = {k.arg for k in value.keywords} & {"default", "default_factory"}
            return not given and (first is None or (isinstance(first, ast.Constant) and first.value is Ellipsis))
        return False

    def takes_any(self, fn):
        """Whether a function takes **kwargs (any name)."""
        _, node, _ = self.defs.get(fn, (None, None, None))
        return isinstance(node, DEFS) and node.args.kwarg is not None

    def call_nodes(self, caller, callee):
        """The calls in `caller` to `callee` (the scan's own resolution, found again by place)."""
        out = []
        for f, line, col in self.sites.get((caller, callee), []) or self._sites_by_class(caller, callee):
            if f not in self._pos:
                self._pos[f] = {(n.lineno, n.col_offset): n for n in ast.walk(self.trees[f]) if isinstance(n, ast.Call)}
            if (line, col) in self._pos[f]:
                out.append((f, self._pos[f][(line, col)]))
        return out

    def _sites_by_class(self, caller, callee):
        # the scan files a call made inside __init__ under the class, and creating an object under the class
        cls = caller.rsplit(".", 1)[0] if caller.endswith(".__init__") else None
        return self.sites.get((cls, callee), []) if cls else []

    def loops(self, fn):
        """The loops written in a function (not in the functions inside it), in order: each with its label (loop 1)."""
        f, node, _ = self.defs[fn]
        found = [n for n in ast.walk(node) if isinstance(n, LOOPS) and self.def_of(f, n) is node]
        found.sort(key=lambda n: (n.lineno, n.col_offset))
        return [(f"loop {i + 1}", n) for i, n in enumerate(found)]

    def loops_around(self, fn, callee):
        """The loops in `fn` that hold a call to `callee`: [(label, loop node)], innermost first."""
        if fn not in self.defs:
            return []
        f, node, _ = self.defs[fn]
        labels = {id(n): label for label, n in self.loops(fn)}
        out = []
        for _, call in self.call_nodes(fn, callee):
            up = self.parent(f, call)
            while up is not None and up is not node:
                if id(up) in labels and (label := labels[id(up)]) not in [x[0] for x in out]:
                    out.append((label, up))
                up = self.parent(f, up)
        return out

    @staticmethod
    def counts(loop):
        """What decides how many times a loop goes round: its iterables (a while loop: its condition)."""
        if isinstance(loop, (ast.For, ast.AsyncFor)):
            return [loop.iter]
        if isinstance(loop, ast.While):
            return [loop.test]
        return [g.iter for g in loop.generators]

    # ------------------------------------------------------------ where a value comes from (backward slicing)
    def trace(self, expr, fn, label, callers, seen=None):
        """Where the value of `expr` (code in function `fn`) comes from. `label` names it if it is itself a value in the
        code ("loop 1", "requests"). `callers`: who really called each function in the run ({fn: {caller}}), else the
        scan's. Returns a list of origins:
          {"fn", "name", "file", "node"}  a value in your code that can be changed (a knob)
          {"input": name, "fn"}         what you typed (the first function's parameter, an argparse option)
          {"outside": text}             something that isn't in the code: a file, another call's result"""
        seen = set() if seen is None else seen
        f = self.defs[fn][0] if fn in self.defs else None
        if literal(expr):
            return [{"fn": fn, "name": label, "file": f, "node": expr}]
        if isinstance(expr, ast.Name):
            return self._trace_name(expr.id, fn, callers, seen)
        if isinstance(expr, ast.Call):
            name = expr.func.attr if isinstance(expr.func, ast.Attribute) else getattr(expr.func, "id", "")
            if name in PASS_THROUGH:
                return [o for a in expr.args for o in self.trace(a, fn, label, callers, seen)]
            if name == "parse_args":
                return [{"argparse": True}]
            return [{"outside": f"what {ast.unparse(expr.func)}() gives"}]
        if isinstance(expr, ast.Attribute):
            base = self.trace(expr.value, fn, label, callers, seen) if not (isinstance(expr.value, ast.Name) and expr.value.id == "self") else []
            if any(o.get("argparse") for o in base):
                return self._option(expr.attr)
            if isinstance(expr.value, ast.Name) and expr.value.id == "self":
                return self._trace_self(expr.attr, fn, callers, seen)
            return base or [{"outside": ast.unparse(expr)}]
        if isinstance(expr, ast.BinOp):
            return self.trace(expr.left, fn, label, callers, seen) + self.trace(expr.right, fn, label, callers, seen)
        if isinstance(expr, ast.UnaryOp):
            return self.trace(expr.operand, fn, label, callers, seen)
        if isinstance(expr, ast.Compare):  # while i < n: the names it is compared with
            return [o for x in [expr.left, *expr.comparators] for o in self.trace(x, fn, label, callers, seen) if "fn" in o or "input" in o]
        if isinstance(expr, (ast.Subscript, ast.Starred)):
            return self.trace(expr.value, fn, label, callers, seen)
        if isinstance(expr, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            return [o for g in expr.generators for o in self.trace(g.iter, fn, label, callers, seen)]
        return [{"outside": ast.unparse(expr)[:60]}]

    def _trace_name(self, name, fn, callers, seen):
        if fn not in self.defs:
            return [{"outside": name}]
        f, node, _ = self.defs[fn]
        if name in [p for p, _ in self.params(fn)]:
            return self._trace_param(fn, name, callers, seen)
        values = [n.value for n in ast.walk(node) if self.def_of(f, n) is node and (
            (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
            or (isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == name and n.value is not None))]
        if values:
            return [o for v in values for o in self.trace(v, fn, name, callers, seen)]
        for n in ast.walk(node):
            if isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)) and name in {x.id for x in ast.walk(n.target) if isinstance(x, ast.Name)}:
                return []  # a loop's own variable, not a size
        mod = self.defs[fn][0] and scan.mod_key(f, self.pkg)
        while (mod, name) not in seen and name in self.imported.get(mod, {}):
            seen.add((mod, name))
            mod, name = self.imported[mod][name]
        value = self.consts.get(mod, {}).get(name)
        if value is not None:
            if literal(value):
                return [{"fn": mod, "name": name, "file": self.mods[mod], "node": value}]
            return [{"outside": f"{mod}.{name}"}]
        return [{"outside": name}]

    def _trace_param(self, fn, name, callers, seen):
        if (fn, name) in seen:
            return []
        seen.add((fn, name))
        default = dict(self.params(fn)).get(name)
        out, called = [], False
        for caller in sorted(callers.get(fn) or self.callers.get(fn) or ()):
            for f, call in self.call_nodes(caller, fn):
                called = True
                arg = self.argument(call, fn, name)
                if arg is None:
                    if default is not None:
                        out += self.trace(default, fn, name, callers, seen)
                elif caller in self.defs:
                    out += self.trace(arg, caller, f"{fn.rsplit('.', 1)[-1]}({name})", callers, seen)
        if not called:  # nothing of yours calls it in this run: you (or a test) gave it
            out.append({"input": name, "fn": fn})
            if default is not None and literal(default):
                out += self.trace(default, fn, name, callers, seen)
        return out

    def _trace_self(self, attr, fn, callers, seen):
        """self.size: what the class's __init__ sets it to."""
        f, _, cls = self.defs.get(fn, (None, None, None))
        if cls is None:
            return [{"outside": f"self.{attr}"}]
        owner = fn.rsplit(".", 1)[0]
        init = f"{owner}.__init__"
        if init not in self.defs:
            fields = dict(self.params(owner))  # a dataclass field
            if attr in fields and fields[attr] is not None:
                return self.trace(fields[attr], owner, attr, callers, seen)
            return [{"outside": f"self.{attr}"}]
        _, node, _ = self.defs[init]
        for n in ast.walk(node):
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self" and t.attr == attr for t in n.targets):
                return self.trace(n.value, init, attr, {**callers, init: callers.get(owner, set())}, seen)
        return [{"outside": f"self.{attr}"}]

    def _option(self, attr):
        """args.jobs: the command-line option --jobs (argparse), and its default when it has one."""
        for fn, (f, node, _) in self.defs.items():
            if not isinstance(node, DEFS):
                continue
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "add_argument" and self.def_of(f, call) is node:
                    flags = [a.value for a in call.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
                    dest = next((k.value.value for k in call.keywords if k.arg == "dest" and isinstance(k.value, ast.Constant)), None)
                    long_flag = next((x for x in flags if x.startswith("--")), flags[0] if flags else "")
                    if (dest or long_flag.lstrip("-").replace("-", "_")) == attr:
                        default = next((k.value for k in call.keywords if k.arg == "default"), None)
                        out = [{"input": long_flag, "fn": fn, "option": True}]
                        if default is not None and literal(default):
                            out.append({"fn": fn, "name": long_flag, "file": f, "node": default, "option": True})
                        return out
        return [{"outside": f"args.{attr}"}]

    def argument(self, call, fn, name):
        """The code a call to `fn` passes for its parameter `name` (by name, or by place), or None when it leaves the
        default. A method called on its object (client.get_item(7)) and a class (Item(7)) count their places after self."""
        for k in call.keywords:
            if k.arg == name:
                return k.value
        names = [p for p, _ in self.params(fn)]
        i = names.index(name) if name in names else -1
        if 0 <= i < len(call.args) and not any(isinstance(a, ast.Starred) for a in call.args[: i + 1]):
            return call.args[i]
        return None

    # ------------------------------------------------------------ a value's place, in any commit (for a change)
    def locate(self, fn, name):
        """(file, node) of the value a change names: a module constant ("batch", "MAX_JOBS"), a parameter's default
        ("lab.load", "requests"), a loop's own values ("lab.main", "loop 1"), an argparse default ("cli.build_parser",
        "--jobs"), a value passed in a call ("lab.main", "load(requests)") or a local name set once ("x.f", "n").
        None when this commit has no such value."""
        if fn in self.mods and fn not in self.defs:
            value = self.consts[fn].get(name)
            return (self.mods[fn], value) if value is not None and literal(value) else None
        if fn not in self.defs:
            return None
        f, node, _ = self.defs[fn]
        if name.startswith("loop "):
            loop = dict(self.loops(fn)).get(name)
            counts = self.counts(loop) if loop is not None else []
            return (f, counts[0]) if len(counts) == 1 and literal(counts[0]) else None
        if name.startswith("-"):
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "add_argument" and any(
                        isinstance(a, ast.Constant) and a.value == name for a in call.args):
                    default = next((k.value for k in call.keywords if k.arg == "default"), None)
                    return (f, default) if default is not None and literal(default) else None
            return None
        if name.endswith(")") and "(" in name:
            callee, param = name[:-1].split("(", 1)
            for target in self.calls.get(fn, ()):
                if target.rsplit(".", 1)[-1] == callee:
                    for _, call in self.call_nodes(fn, target):
                        arg = self.argument(call, target, param)
                        if arg is not None and literal(arg):
                            return (f, arg)
            return None
        default = dict(self.params(fn)).get(name)
        if default is not None:
            return (f, default) if literal(default) else None
        values = [n.value for n in ast.walk(node) if self.def_of(f, n) is node and isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
        return (f, values[0]) if len(values) == 1 and literal(values[0]) else None

    def code(self, f, node):
        return ast.get_source_segment(self.text[f], node)

    def patch(self, f, node, value):
        """[line, col, end line, end col, text]: the value written in place of `node`, on as many lines as before (so
        every line number stays the same). Columns count bytes of the line, as Python's own positions do."""
        text = repr(value)
        if node.end_lineno > node.lineno:
            text = "(" + text + "\n" * (node.end_lineno - node.lineno) + ")"
        return [node.lineno, node.col_offset, node.end_lineno, node.end_col_offset, text]

    # ------------------------------------------------------------ the setup a call needs (any function of yours)
    PLAIN = {"int", "float", "str", "bool", "bytes", "list", "dict", "tuple", "set", "frozenset", "Path", "Sequence",
             "Iterable", "Mapping", "Callable", "Any", "object", "List", "Dict", "Tuple", "Set"}

    def owner(self, fn):
        """The class a method belongs to, or None."""
        cls = self.defs.get(fn, (None, None, None))[2]
        return fn.rsplit(".", 1)[0] if cls is not None else None

    def kind(self, fn):
        """"method" (needs its object), "classmethod", "staticmethod", "function", "class", or None."""
        f, node, cls = self.defs.get(fn, (None, None, None))
        if isinstance(node, ast.ClassDef):
            return "class"
        if not isinstance(node, DEFS):
            return None
        deco = {ast.unparse(d).split(".")[-1] for d in node.decorator_list}
        if cls is None:
            return "function"
        if "classmethod" in deco:
            return "classmethod"
        if "staticmethod" in deco:
            return "staticmethod"
        return "method" if node.args.args and node.args.args[0].arg == "self" else "staticmethod"

    def type_of(self, ann, fn):
        """A type hint as a class of yours ("settings.Settings"), "plain" (int, str, list[...]), or None (unknown)."""
        if ann is None:
            return None
        if isinstance(ann, ast.Constant) and isinstance(ann.value, str):
            try:
                ann = ast.parse(ann.value, mode="eval").body
            except SyntaxError:
                return None
        if isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr):  # X | None
            for side in (ann.left, ann.right):
                t = self.type_of(side, fn)
                if t:
                    return t
            return None
        if isinstance(ann, ast.Subscript):
            head = ast.unparse(ann.value).split(".")[-1]
            if head == "Optional":
                return self.type_of(ann.slice, fn)
            return "plain" if head in self.PLAIN or head.lower() in self.PLAIN else None
        name = ast.unparse(ann)
        if name in ("None", "NoneType"):
            return None
        if name.split(".")[-1] == "Self":
            return self.owner(fn) or (fn if self.kind(fn) == "class" else None)
        if name.split(".")[-1] in self.PLAIN:
            return "plain"
        f = self.defs.get(fn, (None,))[0]
        mod = scan.mod_key(f, self.pkg) if f else None
        head, _, rest = name.partition(".")
        target = None
        if mod and head in self.imported.get(mod, {}):
            m, n = self.imported[mod][head]
            target = f"{m}.{n}" + (f".{rest}" if rest else "")
            if target not in self.defs and f"{n}.{rest}" in self.defs:  # from . import models; models.Settings
                target = f"{n}.{rest}"
        elif mod and f"{mod}.{name}" in self.defs:
            target = f"{mod}.{name}"
        return target if target in self.defs and self.kind(target) == "class" else None

    def methods(self, cls):
        """The names a class answers to (its own and inherited from your classes)."""
        out, todo = set(), [cls]
        while todo:
            c = todo.pop()
            node = self.defs.get(c, (None, None))[1]
            if not isinstance(node, ast.ClassDef):
                continue
            out |= {n.name for n in node.body if isinstance(n, DEFS)}
            todo += [t for b in node.bases if (t := self.type_of(b, c))]
        return out

    def interface(self, cls):
        """Whether a class only describes what others must have (a Protocol or an ABC)."""
        node = self.defs[cls][1]
        return isinstance(node, ast.ClassDef) and any(ast.unparse(b).split(".")[-1] in ("Protocol", "ABC") for b in node.bases)

    def test_calls(self):
        """Calls your tests write with plain values straight in the code: FlakyAPI(script={"/items/7": [503]}),
        Settings(api_key="k"). {callee: [text of the call]}, from tests/ (read, never run)."""
        if hasattr(self, "_test_calls"):
            return self._test_calls
        self._test_calls = {}
        tests = os.path.join(self.export, "tests")
        for d, subs, files in os.walk(tests):
            subs[:] = sorted(s for s in subs if s != "__pycache__")
            for name in sorted(files):
                if not name.endswith(".py"):
                    continue
                try:
                    tree = ast.parse(open(os.path.join(d, name), encoding="utf-8").read())
                except (SyntaxError, UnicodeDecodeError):
                    continue
                names = {}
                for n in tree.body:
                    if isinstance(n, ast.ImportFrom) and n.module and (n.module == self.pkg or n.module.startswith(self.pkg + ".")):
                        mod = n.module[len(self.pkg) + 1:]
                        for a in n.names:
                            names[a.asname or a.name] = f"{mod}.{a.name}" if mod else a.name
                for call in ast.walk(tree):
                    if not isinstance(call, ast.Call) or not all(literal(a) for a in [*call.args, *[k.value for k in call.keywords]]):
                        continue
                    if any(k.arg is None for k in call.keywords):
                        continue
                    head, _, rest = ast.unparse(call.func).partition(".")
                    target = names.get(head)
                    target = f"{target}.{rest}" if target and rest else target
                    if target in self.defs and self.kind(target) in ("class", "function", "classmethod", "staticmethod"):
                        args = [ast.unparse(a) for a in call.args] + [f"{k.arg}={ast.unparse(k.value)}" for k in call.keywords]
                        text = f"{target}({', '.join(args)})"
                        if text not in self._test_calls.setdefault(target, []):
                            self._test_calls[target].append(text)
        for texts in self._test_calls.values():  # the plainest first: FlakyAPI() before FlakyAPI(script={...})
            texts.sort(key=lambda t: (len(ast.parse(t, mode="eval").body.args) + len(ast.parse(t, mode="eval").body.keywords), len(t)))
        return self._test_calls

    def returns(self, fn):
        """The class of yours a function gives back (its return hint; a classmethod's Self), or None."""
        node = self.defs[fn][1]
        if isinstance(node, ast.ClassDef):
            return None if self.interface(fn) else fn  # an interface is made by a class that fits it, never itself
        t = self.type_of(node.returns, fn) if isinstance(node, DEFS) and node.returns is not None else None
        return t if t != "plain" else None

    def needs(self, fn, fakes=()):
        """What calling `fn` needs: ([(param, class of yours)], [plain params without a value]); parameters with a
        default keep it, except an interface one with a fake of yours that fits (so nothing reaches the network)."""
        want, plain = [], []
        node = self.defs[fn][1]
        if isinstance(node, ast.ClassDef):
            owner = self.init_of(fn)
            init = self.defs[owner][1] if owner else None
            hints = {n.target.id: n.annotation for n in node.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
            scope = owner or fn
            if init is not None:
                hints = {a.arg: a.annotation for a in [*init.args.args, *init.args.kwonlyargs]}
        else:
            hints, scope = {a.arg: a.annotation for a in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]}, fn
        for p, default in self.params(fn):
            t = self.type_of(hints.get(p), scope if scope in self.defs else fn)
            if default is None:
                if t and t != "plain":
                    want.append((p, t))
                else:
                    plain.append(p)
            elif t and t != "plain" and self.interface(t) and self.fits(t, fakes):
                want.append((p, t))
        return want, plain

    def fits(self, iface, fakes=()):
        """Classes of yours that fit an interface: all its methods (the set of their names holds the interface's), fakes
        first. Found by intersecting, per method name, the classes that have it."""
        need = {m for m in self.methods(iface) if not m.startswith("_")}
        if not hasattr(self, "_by_method"):
            self._by_method = {}
            for c in (c for c in self.defs if self.kind(c) == "class"):
                for m in self.methods(c):
                    self._by_method.setdefault(m, set()).add(c)
        found = set.intersection(*(self._by_method.get(m, set()) for m in need)) if need else set()
        found = {c for c in found if c != iface and not self.interface(c)}
        fake = lambda c: c in fakes or c.rsplit(".", 1)[-1].startswith(("Fake", "Mock", "Stub", "Dummy"))  # noqa: E731
        return sorted(found, key=lambda c: (not fake(c), c))

    def recipes(self, fakes=()):
        """How to make each class of yours, by forward chaining (each builder a rule: "Settings AND HttpTransport ->
        AiofetchClient", with a counter of what it still misses): {class: the code that makes it}. Builders, best first:
        a call your tests write with plain values; a function of yours that gives one back; the class itself (an enum:
        its first member); for an interface, a class that fits it (fakes first). The queue gives each class its shortest chain."""
        key = tuple(fakes)
        if getattr(self, "_recipes", (None,))[0] == key:
            return self._recipes[1]
        fake = lambda c: c in fakes or c.rsplit(".", 1)[-1].startswith(("Fake", "Mock", "Stub", "Dummy"))  # noqa: E731
        builders = []  # [class, call, [(param, class)], rank]: a fake that needs nothing goes first, so an interface gets it
        for callee, texts in self.test_calls().items():
            t = self.returns(callee)
            if t:
                builders += [(t, text, [], -1 if fake(t) else 0) for text in texts]
        for fn in self.defs:
            if "<" in fn or fn.rsplit(".", 1)[-1].startswith("_") or self.kind(fn) not in ("function", "classmethod", "staticmethod", "class"):
                continue
            t = self.returns(fn)
            if not t:
                continue
            want, plain = self.needs(fn, fakes)
            if not plain:
                builders.append((t, fn, want, -1 if fake(t) and not want else 1 if self.kind(fn) != "class" else 2))
        for iface in (c for c in self.defs if self.kind(c) == "class" and self.interface(c)):
            builders += [(iface, None, [(None, c)], 3) for c in self.fits(iface, fakes)]
        for cls in (c for c in self.defs if self.kind(c) == "class" and self.enum(c) and self.members(c)):
            builders.append((cls, f"{cls}.{self.members(cls)[0]}", [], 2))  # an enum: its first member
        builders.sort(key=lambda b: b[3])
        waiting, missing, made = {}, [], {}
        queue = []
        for i, (t, call, want, _) in enumerate(builders):
            missing.append(len(want))
            for _, need in want:
                waiting.setdefault(need, []).append(i)
            if not want and t not in made:
                made[t] = call if "(" in call or call not in self.defs else f"{call}()"  # a member is no call
                queue.append(t)
        while queue:  # breadth first: each class is made by the first builder that has everything it needs
            ready = queue.pop(0)
            for i in waiting.get(ready, []):
                missing[i] -= 1
                t, call, want, _ = builders[i]
                if missing[i] == 0 and t not in made:
                    made[t] = made[want[0][1]] if call is None else f"{call}({', '.join(f'{p}={made[c]}' for p, c in want)})"
                    queue.append(t)
        self._recipes = (key, made)
        return made

    def build(self, fn, given, fakes=()):
        """The code that calls `fn` with everything it needs: your values (`given`: {param: code}) and the rest made by
        the recipes. Returns (code, []) or (None, [what nothing can make: (param, its class or None)])."""
        made = self.recipes(fakes)
        kind, asks, given = self.kind(fn), [], dict(given)
        head = fn
        if kind == "method":
            cls = self.owner(fn)
            obj = given.pop("self", None) or made.get(cls)  # your pick for the object, else its recipe
            if obj is None:
                asks.append(("self", cls))
            head = f"{obj or cls}.{fn.rsplit('.', 1)[-1]}"
        want, plain = self.needs(fn, fakes)
        args = [f"{p}={code}" for p, code in given.items()]
        for p, t in want:
            if p not in given:
                (args.append(f"{p}={made[t]}") if t in made else asks.append((p, t)))
        asks += [(p, None) for p in plain if p not in given]
        return (None, asks) if asks else (f"{head}({', '.join(args)})", [])

    def starts(self):
        """Functions of yours that run with nothing given (main(), a function whose parameters all have defaults)."""
        return sorted(fn for fn in self.defs if self.kind(fn) == "function" and not fn.rsplit(".", 1)[-1].startswith("_")
                      and "<" not in fn and all(d is not None for _, d in self.params(fn)))

    def reach(self):
        """One breadth-first search from every start at once: parent[fn], the call before it on the shortest way from
        a start (a start's own parent is None)."""
        if not hasattr(self, "_reach"):
            parent = {s: None for s in self.starts()}
            frontier = list(parent)
            while frontier:
                nxt = []
                for fn in frontier:
                    for callee in sorted(self.calls.get(fn, ())):
                        if callee not in parent:
                            parent[callee] = fn
                            nxt.append(callee)
                frontier = nxt
            self._reach = parent
        return self._reach

    def way_to(self, fn):
        """[start, ..., fn]: the shortest way your code reaches `fn` from a start, or None."""
        parent = self.reach()
        if fn not in parent or parent[fn] is None:
            return None
        path = [fn]
        while parent[path[-1]] is not None:
            path.append(parent[path[-1]])
        return path[::-1]
