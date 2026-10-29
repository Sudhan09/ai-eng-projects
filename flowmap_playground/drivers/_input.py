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
        if (inspect.isfunction(obj) or inspect.ismethod(obj) or inspect.isclass(obj)) and (obj.__module__ or "").split(".")[0] == pkg:
            return obj
    raise ValueError(f"there's no function {name} in your code")


def run_call(text):
    """record.parse_line("2026-10-02T09:15:01Z ERROR db: down"): one of your functions, called with plain values.
    The values are read as data (text, numbers, lists, dicts, True/False/None), never run as code."""
    import ast
    import asyncio
    import inspect
    try:
        call = ast.parse(text.strip(), mode="eval").body
        if not isinstance(call, ast.Call) or any(k.arg is None for k in call.keywords):
            raise ValueError
        args = [ast.literal_eval(a) for a in call.args]
        kwargs = {k.arg: ast.literal_eval(k.value) for k in call.keywords}
        name = ast.unparse(call.func)
    except (SyntaxError, ValueError, TypeError):
        raise ValueError('call one of your functions with plain values, e.g. record.parse_line("some text", 3)') from None
    out = yours(name)(*args, **kwargs)
    return asyncio.run(out) if inspect.iscoroutine(out) else out


def with_call(parts, hint):
    """Every Part also gets "call": type any function of yours with plain values (hint: an example from this week)."""
    for block in parts.values():
        block["entries"].setdefault("call", {"label": "a function of yours", "hint": hint, "run": run_call})
    return parts
