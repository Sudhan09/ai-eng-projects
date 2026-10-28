"""Record one test run as JSON events (every call, return, object change), so the map can show real values.

usage: python trace.py <export_dir> <test_file>::<test_name> <out.json>   (a pytest id: tests/unit/test_a.py::test_b)
       python trace.py <export_dir> play:<driver.py>:<entry> <out.json> "<your input>"   (a playground run)
Run it with the project's own Python. The package is the folder under src/ that has an __init__.py.
pytest runs the test, so fixtures, autouse setup, async tests and parametrize all work. Only the test's body is
recorded (a parametrized test: its first case). FLOWMAP_CODE_DIRS="scripts,examples" adds Python outside src/.
While recording, every connection that isn't to this machine is refused.
"""

import asyncio
import concurrent.futures
import contextlib
import dataclasses
import gc
import importlib
import importlib.util
import inspect
import io
import json
import linecache
import logging
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import time
import types

# compiled files go to a fresh folder for this recording only: pytest's cached test files keep the folder they were
# made in, so after a move (flowmap/ became flowmap_tests/) the test code would look like it lives somewhere else
sys.pycache_prefix = tempfile.mkdtemp(prefix="flowmap-pyc-")

import pytest  # noqa: E402

W3 = os.path.abspath(sys.argv[1])
RUN = sys.argv[2]
OUT = os.path.abspath(sys.argv[3])
SRC = os.path.join(W3, "src")
TESTS = os.path.join(W3, "tests")
EXTRA = [os.path.join(W3, d.strip()) for d in os.environ.get("FLOWMAP_CODE_DIRS", "").split(",") if d.strip()]
sys.path[:0] = [SRC, TESTS]
_file, _, _name = RUN.partition("::")
NODE = RUN if _file.endswith(".py") else f"tests/{_file}.py::{_name}"  # the old form: test_module::test_fn
# a playground run calls one entry of a driver (flowmap_playground/drivers/w4.py) with your input instead of a test.
# The entry is recorded as the test would be (hidden "you" frame, so START is your call); the rest of the driver isn't
PLAY = RUN.startswith("play:")
DRIVER, ENTRY = (os.path.abspath(RUN[len("play:"):].rsplit(":", 1)[0]), RUN.rsplit(":", 1)[1]) if PLAY else (None, None)

try:
    import httpx  # noqa: E402
except ImportError:  # a project without httpx: those value shapes simply never match
    httpx = types.SimpleNamespace(Response=(), Request=(), AsyncClient=(), MockTransport=())
try:
    import numpy as np  # noqa: E402
except ImportError:
    np = types.SimpleNamespace(ndarray=(), generic=())

# every module that exists in this snapshot of the repo (a mid-project commit has fewer), subpackages too
PKG = next(d for d in sorted(os.listdir(SRC)) if os.path.isfile(os.path.join(SRC, d, "__init__.py")))
PKG_DIR = os.path.join(SRC, PKG)
MODS = []
for _d, _subs, _files in os.walk(PKG_DIR):
    _subs[:] = sorted(s for s in _subs if os.path.isfile(os.path.join(_d, s, "__init__.py")))
    _dotted = os.path.relpath(_d, SRC).replace(os.sep, ".")
    MODS += [_dotted + "." + f[:-3] if f != "__init__.py" else _dotted for f in sorted(_files)
             if f.endswith(".py") and f != "__main__.py" and not (f == "__init__.py" and _d == PKG_DIR)]
for _m in MODS:
    try:
        importlib.import_module(_m)
    except Exception as exc:  # e.g. an adapter whose library isn't installed: its code just isn't recorded
        print(f"skip module {_m}: {exc!r}"[:200], file=sys.stderr)

# ---------------------------------------------------------------- which code is "yours"
ROOTS = tuple(d + os.sep for d in (PKG_DIR, TESTS, *EXTRA))
codes = set()


def walk_code(co):
    codes.add(co)
    for c in co.co_consts:
        if isinstance(c, types.CodeType):
            walk_code(c)


def add_fn(f, seen=None):
    seen = seen or set()
    if id(f) in seen:
        return
    seen.add(id(f))
    if isinstance(f, (staticmethod, classmethod)):
        f = f.__func__
    if isinstance(f, property):
        f = f.fget
    if isinstance(f, types.FunctionType):
        if f.__code__.co_filename == "<string>" and f.__name__ != "__init__":
            return  # dataclass-made __repr__/__eq__: not your code
        if f.__code__.co_filename == "<string>" or f.__code__.co_filename.startswith(ROOTS):
            walk_code(f.__code__)  # not a library's: Enum.__new__ on your enum, contextlib's wrapper round your function
        # a decorator (like @timed) hides the real function: look inside the wrapper
        inner = getattr(f, "__wrapped__", None)
        if inner is not None:
            add_fn(inner, seen)
        for cell in f.__closure__ or ():
            try:
                v = cell.cell_contents
            except ValueError:
                continue
            if isinstance(v, types.FunctionType) and v.__code__.co_filename.startswith(SRC):
                add_fn(v, seen)


def collect():
    """Your code: the package, the extra code folders, and the test files (the test's module, helpers, conftest.py)."""
    for m in list(sys.modules.values()):
        if not (getattr(m, "__file__", None) or "").startswith(ROOTS):
            continue
        for obj in list(vars(m).values()):
            if getattr(obj, "__module__", None) != m.__name__:
                continue
            if isinstance(obj, types.FunctionType):
                if not obj.__name__.startswith("pytest_"):  # a conftest hook is pytest's machinery, not the test
                    add_fn(obj)
            elif isinstance(getattr(obj, "__wrapped__", None), types.FunctionType):  # @lru_cache, @cache
                add_fn(obj.__wrapped__)
            elif isinstance(obj, type):
                for v in vars(obj).values():
                    add_fn(v)


def mod_of(path):
    """A file's module as the map names it: batch, adapters.alpha (src/), test_part3 (tests/), scripts.seed."""
    if path == DRIVER:
        return "test_playground"
    if path.startswith(PKG_DIR + os.sep):
        rel = os.path.relpath(path, PKG_DIR)[:-3].replace(os.sep, ".")
        return rel[: -len(".__init__")] if rel.endswith(".__init__") else rel
    if any(path.startswith(d + os.sep) for d in EXTRA):
        return os.path.relpath(path, W3)[:-3].replace(os.sep, ".")
    return os.path.basename(path)[:-3]


def mod_name(cls):
    f = getattr(sys.modules.get(cls.__module__), "__file__", None)
    return mod_of(f) if f else cls.__module__.split(".")[-1]


def node_of(code, frame):
    q = code.co_qualname
    if code.co_filename == "<string>":  # dataclass __init__
        cls = type(frame.f_locals.get("self"))
        return f"{mod_name(cls)}.{cls.__qualname__}.__init__"
    head, *inner = q.split(".<locals>.")
    return mod_of(code.co_filename) + "." + head + "".join(f".<{p}>" for p in inner)


def pkg_of(path):
    if "site-packages" in path:
        return path.split("site-packages" + os.sep)[1].split(os.sep)[0]
    m = re.search(r"python3\.\d+/([^/]+)", path)
    if m:
        name = m.group(1)
        return name[:-3] if name.endswith(".py") else name
    return path


# ---------------------------------------------------------------- value snapshots
objs = {}  # id(obj) -> record
keep = []  # strong refs so ids are never reused
counts = {}
tasks = {}  # task -> label
task_creator = {}  # task -> call id


def is_repo_obj(v):
    return type(v).__module__.startswith(PKG + ".")


def obj_rec(v, born_by=None):
    rec = objs.get(id(v))
    if rec is None:
        cls = type(v)
        counts[cls.__name__] = counts.get(cls.__name__, 0) + 1
        rec = {
            "id": f"o{len(objs) + 1}",
            "cls": f"{mod_name(cls)}.{cls.__qualname__}",
            "name": f"{cls.__name__}#{counts[cls.__name__]}",
            "born": born_by,
            "last": None,
        }
        objs[id(v)] = rec
        keep.append(v)
    return rec


# a value's text never carries a local path: "running at /home/me/x/src/pkg/batch.py:80" becomes "running at batch.py:80"
LOCAL_PATH = re.compile(r"(?:[A-Za-z]:)?(?:[/\\][^\s'\"<>:/\\]+)+[/\\]([^\s'\"<>:/\\]+\.py)")


# and a file or folder on this machine keeps only its name: "/tmp/pytest-of-me/pytest-3/test_a0/rows.jsonl" -> "…/rows.jsonl",
# "/tmp/flowmap-play-x1/" -> "…/flowmap-play-x1"
MACHINE_PATH = re.compile(r"(?<![\w/:.])(?:/tmp|/home|/Users|/var|/private|[A-Za-z]:\\)[^\s'\"<>]*?([^\s'\"<>/\\]+)[/\\]?(?=[\s'\"<>]|$)")


def short(s, n=70):
    s = MACHINE_PATH.sub(r"…/\1", LOCAL_PATH.sub(r"\1", str(s)))
    return s if len(s) <= n else s[: n - 1] + "…"


def fields_of(v):
    if dataclasses.is_dataclass(v):
        return [(f.name, getattr(v, f.name)) for f in dataclasses.fields(v)]
    d = dict(vars(v))
    if isinstance(v, BaseException):
        if "url" in d or "reason" in d:
            d = {"url": d.get("url"), "reason": d.get("reason"), **d}
        if hasattr(type(v), "transient"):
            d["transient"] = type(v).transient
    return list(d.items())


def snap(v, depth=2):
    t = type(v)
    if v is None:
        return {"t": "None"}
    if t is bool:
        return {"t": "bool", "v": v}
    if t is int:
        return {"t": "int", "v": v}
    if t is float:
        return {"t": "float", "v": round(v, 6)}
    if t is str:
        return {"t": "str", "v": short(v, 80)}
    if isinstance(v, np.ndarray):
        d = {"t": "ndarray", "dtype": str(v.dtype), "shape": list(v.shape)}
        if v.size <= 64:
            d["v"] = np.round(v.astype(float), 4).tolist()
        return d
    if isinstance(v, np.generic):
        return {"t": f"np.{t.__name__}", "v": round(float(v), 6)}
    if t in (list, tuple):
        d = {"t": t.__name__, "n": len(v)}
        if depth > 0:
            d["items"] = [snap(x, depth - 1) for x in v[:12]]
        return d
    if t is dict:
        d = {"t": "dict", "n": len(v)}
        if depth > 0:
            d["items"] = [[str(k), snap(x, depth - 1)] for k, x in list(v.items())[:12]]
        return d
    if is_repo_obj(v):
        rec = obj_rec(v)
        d = {"t": type(v).__name__, "obj": rec["id"], "name": rec["name"]}
        if isinstance(v, BaseException):
            d["msg"] = short(str(v), 90)
        if depth > 0:
            d["fields"] = [[k, snap(x, depth - 1)] for k, x in fields_of(v) if not callable(x)]
        return d
    if isinstance(v, BaseException):
        return {"t": t.__name__, "msg": short(str(v), 90), "lib": t.__module__.split(".")[0]}
    if isinstance(v, httpx.Response):
        return {"t": "Response", "lib": "httpx", "v": f"<Response [{v.status_code} {v.reason_phrase}]>"}
    if isinstance(v, httpx.Request):
        return {"t": "Request", "lib": "httpx", "v": f"{v.method} {v.url}"}
    if isinstance(v, httpx.AsyncClient):
        return {"t": "AsyncClient", "lib": "httpx", "v": f"AsyncClient(base_url='{v.base_url}')"}
    if isinstance(v, httpx.MockTransport):
        handler = getattr(v, "handler", None)
        name = getattr(handler, "__qualname__", None) or type(handler).__name__
        return {"t": "MockTransport", "lib": "httpx", "v": f"MockTransport(handler={name})"}
    if inspect.iscoroutine(v):
        return {"t": "coroutine", "v": f"<coroutine {v.__qualname__}>"}
    if isinstance(v, asyncio.Task):
        return {"t": "Task", "lib": "asyncio", "v": tasks.get(v, "Task")}
    if isinstance(v, asyncio.BoundedSemaphore):
        return {"t": "BoundedSemaphore", "lib": "asyncio", "v": f"{v._value} permits free"}
    if isinstance(v, (types.FunctionType, types.MethodType, types.BuiltinFunctionType, types.BuiltinMethodType)):
        return {"t": "function", "v": getattr(v, "__qualname__", repr(v))}
    lib = t.__module__.split(".")[0]
    return {"t": t.__name__, "lib": lib, "v": short(repr(v), 80)}


def field_view(v):
    """One compact string per field, used to spot changes between events."""
    if is_repo_obj(v):
        return obj_rec(v)["name"]
    if isinstance(v, asyncio.BoundedSemaphore):
        return f"{v._value} permits free"
    if isinstance(v, asyncio.Lock):
        return "locked" if v.locked() else "unlocked"
    if isinstance(v, httpx.AsyncClient):
        return f"AsyncClient(base_url='{v.base_url}')"
    if isinstance(v, float):
        return repr(round(v, 4))
    return short(repr(v), 80)


# ---------------------------------------------------------------- the recorder
events = []
calls = {}  # call id -> dict(frame=..., node=...)
live = {}  # id(frame) -> call id
t0 = time.perf_counter()
watch = []  # repo objects whose fields we diff
threads = {}  # thread id -> lane label (TH1, TH2): to_thread, a TestClient's server thread
_tl = threading.local()  # per thread: busy (inside a recorder callback), creator (the call that sent work here)
_lock = threading.Lock()
recording = False  # only the test's body: fixture setup and teardown stay out


def enter():
    """True when this thread isn't already inside a recorder callback (the recorder's own calls are never recorded)."""
    if getattr(_tl, "busy", False):
        return False
    _tl.busy = True
    return True


def thread_lane():
    if threading.current_thread() is threading.main_thread():
        return None
    return threads.setdefault(threading.get_ident(), f"TH{len(threads) + 1}")


def task_label():
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    if task is not None and (task in tasks or not thread_lane()):
        return tasks.setdefault(task, "main")
    return thread_lane() or "sync"


MAX_EVENTS = 20_000


def emit(kind, **kw):
    if len(events) >= MAX_EVENTS:
        return kw
    kw = {"k": kind, **kw}
    kw.setdefault("task", task_label())
    with _lock:
        kw["i"] = len(events)
        kw["t"] = round((time.perf_counter() - t0) * 1000, 3)
        events.append(kw)
    return kw


def diff_objects(by):
    for v in watch:
        rec = objs[id(v)]
        now = {k: field_view(x) for k, x in fields_of(v) if not callable(x)}
        old = rec["last"]
        if old is not None:
            for k, x in now.items():
                if old.get(k) != x:
                    emit("set", obj=rec["id"], field=k, old=old.get(k), new=x, by=by)
        rec["last"] = now


def rel(path):
    """A file as the map names it: relative to the project; a playground driver counts as the test."""
    if path.startswith("<"):  # "<string>": the __init__ a dataclass writes is no file (relpath would add the folder we're in)
        return path
    return "tests/playground.py" if path == DRIVER else os.path.relpath(path, W3)


def call_line(frame):
    if frame is None:
        return None
    line = linecache.getline(frame.f_code.co_filename, frame.f_lineno).strip()
    return {"file": rel(frame.f_code.co_filename), "line": frame.f_lineno, "text": line}


def live_call(f):
    """The nearest call still running at or above this frame."""
    while f is not None:
        cid = live.get(id(f))
        if cid is not None and calls[cid]["frame"] is f:
            return cid
        f = f.f_back
    return None


def find_parent(frame):
    up = frame.f_back
    # the recorder's own wrapper (submit's job), and a driver's own helpers (only its entry is recorded)
    while up is not None and up.f_code.co_filename in (__file__, DRIVER) and up.f_code not in codes:
        up = up.f_back
    via = None
    if up is not None and up.f_code not in codes:
        via = pkg_of(up.f_code.co_filename)
        if up.f_code.co_qualname == "Handle._run":  # a task's first frame
            try:
                task = asyncio.current_task()
            except RuntimeError:
                task = None
            if task in task_creator:
                return task_creator[task], "asyncio"
    cid = live_call(up)
    if cid is None and thread_lane():
        # another thread: the call that sent the work here (to_thread), else the call the main thread is waiting in
        # (a TestClient request runs the app in a server thread while the test waits)
        cid = getattr(_tl, "creator", None) or live_call(sys._current_frames().get(threading.main_thread().ident))
    return cid, via if cid else None  # the test itself: pytest called it


def args_of(code, frame):
    n = code.co_argcount + code.co_kwonlyargcount
    names = list(code.co_varnames[:n])
    if code.co_flags & inspect.CO_VARARGS:
        names.append(code.co_varnames[n])
        n += 1
    if code.co_flags & inspect.CO_VARKEYWORDS:
        names.append(code.co_varnames[n])
    loc = frame.f_locals
    return [(nm, loc[nm]) for nm in names if nm in loc]


def locals_of(code, frame, skip, depth=1):
    out = []
    for k, v in frame.f_locals.items():
        if k in skip or k == "self" or k.startswith(("__", "@")):  # "@py_assert1": pytest's rewritten asserts
            continue
        if isinstance(v, types.ModuleType):
            continue
        out.append([k, snap(v, depth)])
    return out[:10]


def on_start(code, offset):
    if not enter():
        return
    try:
        frame = sys._getframe(1)
        node = node_of(code, frame)
        if code.co_name == "__init__" and is_repo_obj(frame.f_locals.get("self")):
            cls = type(frame.f_locals["self"])  # inherited __init__ still makes this class
            node = f"{mod_name(cls)}.{cls.__qualname__}.__init__"
        parent, via = find_parent(frame)
        diff_objects(parent)
        cid = f"c{len(calls) + 1}"
        args = args_of(code, frame)
        self_obj = frame.f_locals.get("self")
        is_new = node.endswith(".__init__")
        if is_new and self_obj is not None:
            # super().__init__ inside an __init__ is the same birth, not a new object
            if id(self_obj) in objs and objs[id(self_obj)].get("init_open"):
                calls[cid] = {"frame": frame, "node": node, "quiet": True}
                live[id(frame)] = cid
                return
            rec = obj_rec(self_obj, born_by=parent)
            rec["init_open"] = cid
        calls[cid] = {"frame": frame, "node": node, "quiet": False, "args": args}
        live[id(frame)] = cid
        ev = {
            "id": cid,
            "fn": node[: -len(".__init__")] if is_new else node,
            "parent": parent,
            "via": via,
            "args": [[k, snap(v)] for k, v in args if k != "self"],
            "site": call_line(calls[parent]["frame"] if parent else None),
            "def": {"file": rel(code.co_filename) if code.co_filename != "<string>" else None, "line": code.co_firstlineno},
        }
        if self_obj is not None and is_repo_obj(self_obj):
            ev["self"] = obj_rec(self_obj)["id"]
        if code.co_flags & inspect.CO_COROUTINE:
            ev["async"] = True
        emit("new" if is_new else "call", **ev)
    finally:
        _tl.busy = False


def finish(code, frame, kind, payload):
    cid = live.pop(id(frame), None)
    if cid is None:
        return
    info = calls[cid]
    if info.get("quiet"):
        return
    diff_objects(cid)
    node = info["node"]
    names = {k for k, _ in info["args"]}
    ev = {"id": cid, "fn": node[: -len(".__init__")] if node.endswith(".__init__") else node}
    if kind == "return":
        ev["value"] = snap(payload)
    else:
        ev["exc"] = snap(payload)
    ev["locals"] = locals_of(code, frame, names, 3 if cid == "c1" else 1)
    if node.endswith(".__init__"):
        self_obj = frame.f_locals.get("self")
        rec = objs[id(self_obj)]
        rec.pop("init_open", None)
        ev["obj"] = snap(self_obj)
        if self_obj not in watch and not isinstance(self_obj, BaseException):
            watch.append(self_obj)
            rec["last"] = {k: field_view(x) for k, x in fields_of(self_obj) if not callable(x)}
        emit("born" if kind == "return" else "raise", **ev)
    else:
        emit(kind, **ev)


def on_return(code, offset, retval):
    if not enter():
        return
    try:
        finish(code, sys._getframe(1), "return", retval)
    finally:
        _tl.busy = False


def on_unwind(code, offset, exc):
    if code not in codes or not enter():
        return
    try:
        finish(code, sys._getframe(1), "raise", exc)
    finally:
        _tl.busy = False


def on_handled(code, offset, exc):
    if code not in codes or not enter():
        return
    try:
        frame = sys._getframe(1)
        cid = live.get(id(frame))
        if cid and not calls[cid].get("quiet"):
            emit("catch", id=cid, fn=calls[cid]["node"], exc=snap(exc), at=call_line(frame))
    finally:
        _tl.busy = False


def on_raise(code, offset, exc):
    if code not in codes or not enter():
        return
    try:
        frame = sys._getframe(1)
        cid = live.get(id(frame))
        if cid and not calls[cid].get("quiet"):
            emit("throw", id=cid, fn=calls[cid]["node"], exc=snap(exc), at=call_line(frame))
    finally:
        _tl.busy = False


def yielded(code, value):
    """What a generator handed out at this yield, as a 1-tuple; None when the frame only waits (an await)."""
    if code.co_name == "<genexpr>":  # (f(x) for x in xs) is an expression, not a function you wrote
        return None
    if code.co_flags & inspect.CO_ASYNC_GENERATOR:
        if type(value).__name__ == "async_generator_wrapped_value":  # `yield x` in an async generator wraps x
            inner = gc.get_referents(value)
            return (inner[0],) if inner else None
        return None  # an await inside the async generator
    if code.co_flags & inspect.CO_GENERATOR and not code.co_flags & inspect.CO_COROUTINE:
        return (value,)
    return None


def on_yield(code, offset, value):
    if not enter():
        return
    try:
        frame = sys._getframe(1)
        cid = live.get(id(frame))
        if cid and not calls[cid].get("quiet"):
            diff_objects(cid)
            out = yielded(code, value)
            if out:  # a generator's output: each value it yields
                emit("yield", id=cid, fn=calls[cid]["node"], value=snap(out[0]), at=call_line(frame))
            emit("pause", id=cid, fn=calls[cid]["node"], at=call_line(frame))
    finally:
        _tl.busy = False


def on_resume(code, offset):
    if not enter():
        return
    try:
        frame = sys._getframe(1)
        cid = live.get(id(frame))
        if cid and not calls[cid].get("quiet"):
            emit("resume", id=cid, fn=calls[cid]["node"])
    finally:
        _tl.busy = False


# a task's parent is the call that created it (fetch_many), not the event loop. Every task starts in
# loop.create_task: TaskGroup.create_task, asyncio.create_task and gather all go through it.
_create_task = asyncio.BaseEventLoop.create_task
# the helpers that hand a coroutine on to loop.create_task; asyncio's own tasks (a server accepting a connection) come
# from elsewhere in asyncio and get no lane
TASK_HELPERS = tuple(os.path.join(os.path.dirname(asyncio.__file__), f) for f in ("tasks.py", "taskgroups.py"))


def create_task(self, coro, *a, **kw):
    task = _create_task(self, coro, *a, **kw)
    was = getattr(_tl, "busy", False)
    if not recording or was or not self.is_running():  # asyncio.run's first task is the run itself ("main")
        return task
    _tl.busy = True
    try:
        frame = sys._getframe(1)
        while frame is not None and frame.f_code.co_filename in TASK_HELPERS:
            frame = frame.f_back
        if frame is None or frame.f_code not in codes or not hasattr(coro, "cr_code"):
            return task  # asyncio's or a library's own task: no lane of its own
        by = live_call(frame)
        label = f"T{sum(1 for v in tasks.values() if v.startswith('T')) + 1}"
        creator = task_label()
        tasks[task] = label
        task_creator[task] = by
        emit(
            "task",
            task=creator,
            label=label,
            by=by,
            coro={"fn": node_of(coro.cr_code, coro.cr_frame), "args": [[k, snap(v)] for k, v in args_of(coro.cr_code, coro.cr_frame) if k != "self"]},
            site=call_line(frame),
        )
    finally:
        _tl.busy = was
    return task


asyncio.BaseEventLoop.create_task = create_task

# work sent to a thread pool (asyncio.to_thread, run_in_executor) remembers the call that sent it
_submit = concurrent.futures.ThreadPoolExecutor.submit


def submit(self, fn, /, *args, **kwargs):
    by = live_call(sys._getframe(1)) if recording else None

    def job():
        _tl.creator = by
        try:
            return fn(*args, **kwargs)
        finally:
            _tl.creator = None

    return _submit(self, job)


concurrent.futures.ThreadPoolExecutor.submit = submit


# no network while recording: a connection to anything but this machine (Postgres, Ollama on localhost are fine) fails
_connect, _connect_ex = socket.socket.connect, socket.socket.connect_ex


def local_only(addr):
    host = str(addr[0]) if isinstance(addr, tuple) and addr else "localhost"  # a str address is a local Unix socket
    if not (host == "localhost" or host.startswith(("127.", "::ffff:127.")) or host == "::1"):
        raise ConnectionRefusedError(f"flowmap: no network while recording ({host})")


def connect(self, addr):
    local_only(addr)
    return _connect(self, addr)


def connect_ex(self, addr):
    local_only(addr)
    return _connect_ex(self, addr)


socket.socket.connect, socket.socket.connect_ex = connect, connect_ex


class Capture(logging.Handler):
    def emit(self, record):
        if recording:
            emit("log", level=record.levelname, msg=short(record.getMessage(), 140))


logging.getLogger(PKG).addHandler(Capture())

mon = sys.monitoring
T = mon.DEBUGGER_ID
E = mon.events


def start():
    global recording, t0
    collect()
    mon.use_tool_id(T, "flowmap")
    for ev, cb in [
        (E.PY_START, on_start),
        (E.PY_RETURN, on_return),
        (E.PY_UNWIND, on_unwind),
        (E.EXCEPTION_HANDLED, on_handled),
        (E.RAISE, on_raise),
        (E.PY_YIELD, on_yield),
        (E.PY_RESUME, on_resume),
    ]:
        mon.register_callback(T, ev, cb)
    for c in codes:
        mon.set_local_events(T, c, E.PY_START | E.PY_RETURN | E.PY_YIELD | E.PY_RESUME)
    mon.set_events(T, E.PY_UNWIND | E.EXCEPTION_HANDLED | E.RAISE)
    t0 = time.perf_counter()
    recording = True


def stop():
    global recording
    recording = False
    mon.set_events(T, 0)
    for c in codes:
        mon.set_local_events(T, c, 0)
    mon.free_tool_id(T)


status = "not run"


class Recorder:
    """A pytest plugin: one test, its body recorded, its result kept."""

    def pytest_collection_modifyitems(self, items):
        del items[1:]  # a parametrized test runs once: its first case

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_call(self, item):
        start()
        try:
            yield
        finally:
            stop()

    def pytest_collectreport(self, report):
        global status
        if report.skipped:  # pytest.importorskip at the top of the test file
            status = "skipped"

    def pytest_runtest_logreport(self, report):
        global status
        if report.when == "call" and report.passed:
            status = "passed"
        elif report.failed and report.when != "teardown":
            crash = getattr(report.longrepr, "reprcrash", None)
            why = crash.message if crash else str(report.longrepr).strip().splitlines()[-1:]
            status = ("failed: " if report.when == "call" else f"error in {report.when}: ") + short(str(why).splitlines()[0] if why else "", 160)
        elif report.skipped:
            status = "skipped"


played = {}
if PLAY:
    sys.path.insert(0, os.path.dirname(DRIVER))  # the drivers' own helpers (_input.py)
    spec = importlib.util.spec_from_file_location("flowmap_driver", DRIVER)
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    entry = driver.ENTRIES[ENTRY]["run"]
    codes.add(entry.__code__)
    os.chdir(tempfile.mkdtemp(prefix="flowmap-play-"))  # an empty folder: no .env of yours is read, files land here
    printed, errors, result = io.StringIO(), io.StringIO(), None
    status = "passed"
    start()
    try:
        with contextlib.redirect_stdout(printed), contextlib.redirect_stderr(errors):
            result = entry(sys.argv[4])
    except SystemExit as exc:  # argparse refusing your arguments
        result = exc.code
    except BaseException as exc:
        status = f"raised {type(exc).__name__}: {short(str(exc), 140)}"
    finally:
        stop()
    played = {"printed": [short(x, 300) for x in printed.getvalue().splitlines()[:20]],
              "stderr": [short(x, 300) for x in errors.getvalue().splitlines()[:20]],
              "exit": result if isinstance(result, int) and not isinstance(result, bool) else None}
else:
    os.chdir(W3)
    code = pytest.main([NODE, "-q", "-p", "no:cacheprovider", "-o", "addopts="], plugins=[Recorder()])
    if status == "not run":
        status = f"not run: pytest could not collect {NODE} (exit code {int(code)})"

out = {
    "run": f"play:{os.path.basename(DRIVER)}:{ENTRY}" if PLAY else RUN,
    "status": status,
    "events": events,
    "objects": {rec["id"]: {k: rec[k] for k in ("cls", "name", "born")} for rec in objs.values()},
    "tasks": sorted(set(tasks.values()) | set(threads.values())),
    **played,
}
json.dump(out, open(OUT, "w"), indent=0, default=str)
shutil.rmtree(sys.pycache_prefix, ignore_errors=True)
print(RUN, status, len(events), "events,", len(objs), "objects,", len(calls), "calls")
