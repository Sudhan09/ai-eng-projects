"""Your typed words, for the drivers: what to ask for, what the fake server should answer, and the same words made
back from what your tests did (for the Try: suggestions)."""


def scripted(text, path_of=lambda word: word):
    """"/v2/items/7 /items/1=503,503,200" -> (["/v2/items/7", "/items/1"], {"/items/1": [503, 503, 200]}).

    After "=", the fake's answers for that path, in order: status codes, or a word the fake knows ("timeout").
    """
    asks, script = [], {}
    for word in text.split():
        ask, _, answers = word.partition("=")
        asks.append(ask)
        if answers:
            script[path_of(ask)] = [int(a) if a.isdigit() else a for a in answers.split(",") if a]
    return asks, script


def options(text, *names):
    """Pull settings out of your words: ("/items/1 rpm=120", "rpm") -> ("/items/1", {"rpm": "120"})."""
    rest, found = [], {}
    for word in text.split():
        key, eq, value = word.partition("=")
        if eq and key in names:
            found[key] = value
        else:
            rest.append(word)
    return " ".join(rest), found


# ---------------------------------------------------------------- suggestions from your tests (see suggest.py)
# An entry's "from" maps one of your functions to a small rule: the values a test gave that function (and what the test
# did just before, in `before`: its fake's script, its client's settings) -> the words you'd type, or None.

def words(asks, script=None, path_of=lambda ask: ask):
    """scripted() the other way round: (["/items/1", "/items/2"], {"/items/2": [404]}) -> "/items/1 /items/2=404"."""
    out = []
    for ask in asks:
        answers = (script or {}).get(path_of(ask))
        plain = isinstance(answers, list) and answers and all(isinstance(a, (int, str)) and not isinstance(a, bool) and " " not in str(a) for a in answers)
        out.append(f"{ask}=" + ",".join(str(a) for a in answers) if plain else str(ask))
    return " ".join(out)


def last(before, fn, name=None):
    """What the test last gave `fn` before this call: all its values, or the one called `name`."""
    for call in reversed(before):
        if call["fn"] == fn:
            return call["args"] if name is None else call["args"].get(name)
    return None


def few(value, most=6):
    """A short list of words or numbers (paths, ids), or None."""
    ok = isinstance(value, list) and 0 < len(value) <= most
    return value if ok and all(isinstance(v, (str, int)) and not isinstance(v, bool) and " " not in str(v) for v in value) else None


# ---------------------------------------------------------------- "call": any function of yours, with plain values

def yours(name):
    """Your function or class by the map's name ("record.parse_line", "config.ParserConfig.from_lists"), looked up in
    your package only: never a library's, never a name starting with _."""
    import importlib
    import inspect
    import os
    import sys
    src = next(p for p in sys.path if os.path.basename(p.rstrip(os.sep)) == "src")
    pkg = next(d for d in sorted(os.listdir(src)) if os.path.exists(os.path.join(src, d, "__init__.py")))
    parts = name.split(".")
    if not all(p.isidentifier() for p in parts) or any(p.startswith("_") for p in parts[1:]):
        raise ValueError(f"there's no function {name} in your code")
    for i in range(len(parts) - 1, 0, -1):
        try:
            obj = importlib.import_module(pkg if parts[:i] == ["__init__"] else ".".join([pkg, *parts[:i]]))
        except ImportError:
            continue
        for p in parts[i:]:
            obj = getattr(obj, p, None)
        if inspect.ismodule(obj) and parts[0] == "__init__":  # main() in __init__.py, and a main.py: Python gives the module
            raise ValueError(f"{name} can't be called: your module {parts[1]}.py has the same name and hides it")
        plain = inspect.isfunction(obj) or inspect.ismethod(obj) or inspect.isclass(obj)
        cached = inspect.isfunction(getattr(obj, "__wrapped__", None))  # @lru_cache, @cache
        if (plain or cached) and (getattr(obj, "__module__", None) or "").split(".")[0] == pkg:
            return obj
    raise ValueError(f"there's no function {name} in your code")


HINT = 'call one of your functions with plain values, e.g. record.parse_line("some text", 3)'


def run_call(text):
    """record.parse_line("2026-10-02T09:15:01Z ERROR db: down"): one of your functions, called with plain values (text,
    numbers, lists, dicts, True/False/None, a member of an enum of yours) or with what other functions of yours give back:
    client.AiofetchClient.from_settings(settings.get_settings()).get_item(7). Read as data, never run as code: only
    your package's functions and classes can be called, and the methods of what they give back. A context manager one
    of them makes (@contextmanager) is entered for the run; everything async runs on one event loop."""
    import ast
    import asyncio
    import contextlib
    import inspect
    try:
        call = ast.parse(text.strip(), mode="eval").body
    except SyntaxError:
        raise ValueError(HINT) from None
    if not isinstance(call, ast.Call):
        raise ValueError(HINT)
    loop, stack, astack = None, contextlib.ExitStack(), contextlib.AsyncExitStack()

    def on_loop(awaitable):
        nonlocal loop
        loop = loop or asyncio.new_event_loop()
        return loop.run_until_complete(awaitable)

    def done(value):  # a coroutine is awaited, a context manager made by @contextmanager is entered
        if inspect.iscoroutine(value):
            value = on_loop(value)
        if isinstance(value, contextlib._AsyncGeneratorContextManager):
            value = on_loop(astack.enter_async_context(value))
        elif isinstance(value, contextlib._GeneratorContextManager):
            value = stack.enter_context(value)
        return value

    def value(node):
        try:
            return ast.literal_eval(node)
        except ValueError:
            pass
        if isinstance(node, ast.Attribute) and not node.attr.startswith("_"):  # a member of an enum of yours: LogLevel.ERROR
            owner = yours(ast.unparse(node.value))
            if isinstance(owner, type) and issubclass(owner, __import__("enum").Enum) and node.attr in owner.__members__:
                return owner[node.attr]
            raise ValueError(HINT)
        if not isinstance(node, ast.Call) or any(k.arg is None for k in node.keywords) or any(isinstance(a, ast.Starred) for a in node.args):
            raise ValueError(HINT)
        f = callee(node.func)
        return done(f(*[value(a) for a in node.args], **{k.arg: value(k.value) for k in node.keywords}))

    def callee(func):
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Call):  # a method of what a call of yours gave back
            if func.attr.startswith("_"):
                raise ValueError(f"there's no method {func.attr} to call")
            return getattr(value(func.value), func.attr)
        return yours(ast.unparse(func))

    try:
        with stack:
            try:
                return value(call)
            finally:
                if loop is not None:
                    loop.run_until_complete(astack.aclose())
                    loop.close()
    except BaseException as exc:
        if type(exc).__name__ == "FlowmapStop":  # your function returned inside the caller that reached it
            return exc.args[0] if exc.args else None
        raise


def with_call(parts, hint):
    """Every Part also gets "call": type any function of yours with plain values (hint: an example from this week)."""
    for block in parts.values():
        block["entries"].setdefault("call", {"label": "a function of yours", "hint": hint, "run": run_call})
    return parts
