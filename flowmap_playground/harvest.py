"""What your tests pass into your code, for the playground's suggestions. Run with the project's own Python, on one
Part's code:

usage: python harvest.py <export_dir> <out.json>

pytest runs every test under tests/. Each call into your package is noted: the function (named as the map names it,
"client.AiofetchClient.get_item"), the values it got (text, numbers, lists and dicts as they are; other objects by
their type) and how it ended (returned or raised). Nothing else is recorded, so it takes about as long as the tests.
The same guard as the recorder: no network beyond this machine.
"""

import dataclasses
import enum
import json
import os
import socket
import sys
import threading

# compiled files are kept with the recorder's (flowmap_tests/build/pyc/), by each file's full path: each library is
# compiled once, and pytest's compiled test files from another folder are never reused
sys.pycache_prefix = os.environ.get("FLOWMAP_PYC") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "flowmap_tests", "build", "pyc")

import pytest  # noqa: E402

EXPORT = os.path.abspath(sys.argv[1])
OUT = os.path.abspath(sys.argv[2])
SRC, TESTS = os.path.join(EXPORT, "src"), os.path.join(EXPORT, "tests")
sys.path[:0] = [SRC, TESTS]
PKG = next(d for d in sorted(os.listdir(SRC)) if os.path.exists(os.path.join(SRC, d, "__init__.py")))
ROOT = os.path.join(SRC, PKG) + os.sep
PER_FN = 40  # different value sets kept per function
TOOL = sys.monitoring.PROFILER_ID
E = sys.monitoring.events

calls, pending, seen, test = [], {}, {}, None


def plain(v, depth=0):
    """A value as JSON: plain values as they are, anything else as {"@type": its class}."""
    if v is None or isinstance(v, (bool, int, float)):
        return v
    if isinstance(v, str):
        return v if len(v) <= 500 else {"@type": "str"}
    if isinstance(v, enum.Enum):
        return {"@enum": f"{type(v).__name__}.{v.name}"}
    if isinstance(v, os.PathLike):
        return {"@path": os.path.basename(os.fspath(v))}
    if depth < 3 and isinstance(v, (list, tuple, range)) and len(v) <= 50:
        return [plain(x, depth + 1) for x in v]
    if depth < 3 and isinstance(v, (set, frozenset)) and len(v) <= 50:
        return {"@set": sorted((plain(x, depth + 1) for x in v), key=repr)}
    if depth < 3 and isinstance(v, dict) and len(v) <= 50 and all(isinstance(k, (str, int)) for k in v):
        return {str(k): plain(x, depth + 1) for k, x in v.items()}
    if depth < 3 and dataclasses.is_dataclass(v) and not isinstance(v, type):
        return {"@type": type(v).__name__, "@fields": {f.name: plain(getattr(v, f.name, None), depth + 1) for f in dataclasses.fields(v)}}
    return {"@type": type(v).__name__}


def name_of(code):
    """"client.AiofetchClient.get_item", or None for a lambda, a comprehension or a function inside a function."""
    if "<" in code.co_qualname:
        return None
    return os.path.relpath(code.co_filename, ROOT)[:-3].replace(os.sep, ".") + "." + code.co_qualname


def made_by_python(code, frame):
    """The __init__ Python writes for a dataclass of yours (no file): "record.LogRecord.__init__", else None."""
    cls = type(frame.f_locals.get("self"))
    if code.co_name != "__init__" or not (cls.__module__ == PKG or cls.__module__.startswith(PKG + ".")):
        return None
    mod = cls.__module__[len(PKG) + 1:] or "__init__"
    return f"{mod}.{cls.__qualname__}.__init__" if "<" not in cls.__qualname__ else None


def on_start(code, offset):
    if code.co_filename == "<string>":  # one per dataclass: a library's is turned off, yours is kept
        frame = sys._getframe(1)
        fn = made_by_python(code, frame)
        if not fn:
            return sys.monitoring.DISABLE
        if test is None:
            return None
    elif not code.co_filename.startswith(ROOT) or test is None:
        return sys.monitoring.DISABLE if not code.co_filename.startswith(ROOT) else None
    else:
        fn = name_of(code)
        if not fn:
            return sys.monitoring.DISABLE
        frame = sys._getframe(1)
    n = code.co_argcount + code.co_kwonlyargcount + bool(code.co_flags & 0x04) + bool(code.co_flags & 0x08)
    names = code.co_varnames[:n]
    bound = names[0] if names and names[0] in ("self", "cls") else None
    args = {k: plain(frame.f_locals.get(k)) for k in names[1 if bound else 0:]}
    key = (test, fn, json.dumps(args, sort_keys=True, default=str))
    if key in seen or seen.get((test, fn), 0) >= PER_FN:
        return None
    seen[key] = True
    seen[(test, fn)] = seen.get((test, fn), 0) + 1
    rec = {"test": test, "fn": fn, "args": args, "bound": bound, "positional": code.co_argcount - (1 if bound else 0),
           "varargs": bool(code.co_flags & 0x0C), "async": bool(code.co_flags & 0x80), "end": None}
    caller = frame.f_back
    # called by the test itself (not from a thread or through other code): the plainest test to start from
    rec["direct"] = threading.current_thread() is threading.main_thread() and caller is not None and caller.f_code.co_filename.startswith(TESTS + os.sep)
    if bound == "self" and code.co_name == "__init__":  # an inherited __init__: the class it was making
        rec["makes"] = type(frame.f_locals.get("self")).__qualname__
    calls.append(rec)
    pending[id(frame)] = rec
    return None


def on_return(code, offset, value):
    if not code.co_filename.startswith(ROOT) and code.co_filename != "<string>":
        return sys.monitoring.DISABLE
    rec = pending.pop(id(sys._getframe(1)), None)
    if rec:
        rec["end"] = "returned " + type(value).__name__
    return None


def on_unwind(code, offset, exc):
    rec = pending.pop(id(sys._getframe(1)), None)
    if rec:
        rec["end"] = "raised " + type(exc).__name__


class Harvest:
    """Which test is running: every call is noted under it."""

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        global test
        test = item.nodeid
        yield
        test = None


_connect = socket.socket.connect


def local_only(self, addr):
    """Only this machine: a test that reached for the real network fails instead of spending anything."""
    host = addr[0] if isinstance(addr, tuple) else addr
    if isinstance(host, str) and host not in ("127.0.0.1", "::1", "localhost") and self.family in (socket.AF_INET, socket.AF_INET6):
        raise ConnectionRefusedError(f"flowmap: no network while recording ({host})")
    return _connect(self, addr)


socket.socket.connect = local_only
os.chdir(EXPORT)
sys.monitoring.use_tool_id(TOOL, "flowmap-harvest")
sys.monitoring.register_callback(TOOL, E.PY_START, on_start)
sys.monitoring.register_callback(TOOL, E.PY_RETURN, on_return)
sys.monitoring.register_callback(TOOL, E.PY_UNWIND, on_unwind)
sys.monitoring.set_events(TOOL, E.PY_START | E.PY_RETURN | E.PY_UNWIND)
try:
    code = pytest.main(["tests", "-q", "-p", "no:cacheprovider", "-o", "addopts="], plugins=[Harvest()])
finally:
    sys.monitoring.set_events(TOOL, 0)
    sys.monitoring.free_tool_id(TOOL)
json.dump({"package": PKG, "exit": int(code), "calls": calls}, open(OUT, "w"), indent=0)
print(f"{len(calls)} calls from {len({c['test'] for c in calls})} tests, pytest exit {int(code)}")
