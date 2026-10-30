"""How long the playground's steps take, measured (never estimated). Runs in a throwaway folder: your runs/ are copied,
never changed.

usage: python3 flowmap_playground/tests/bench.py            the playground's steps
       python3 flowmap_playground/tests/bench.py --hook     also the tests map's rebuild, phase by phase (as your
                                                            commit hook runs it; it rebuilds flowmap_tests/build)
"""

import collections
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PLAYGROUND = os.path.dirname(HERE)
sys.path.insert(0, PLAYGROUND)
import server  # noqa: E402
import flowmap  # noqa: E402
import pickruns  # noqa: E402


def timed(f, *a, n=3, **k):
    """The fastest of n tries (the others are the machine being busy), and what the last one gave."""
    best, out = None, None
    for _ in range(n):
        t = time.perf_counter()
        try:
            out = f(*a, **k)
        except ValueError as exc:
            out = exc
        took = time.perf_counter() - t
        best = took if best is None else min(best, took)
    return best, out


def playground():
    home = tempfile.mkdtemp(prefix="flowmap-bench-")
    os.symlink(os.path.join(PLAYGROUND, "drivers"), os.path.join(home, "drivers"))
    if os.path.isdir(os.path.join(PLAYGROUND, "runs")):
        shutil.copytree(os.path.join(PLAYGROUND, "runs"), os.path.join(home, "runs"))
    server.HERE = home
    found = server.projects()
    rows = []
    try:
        for key, p in found.items():
            took, _ = timed(server.build, key, p, log=lambda m: None)
            rows.append((f"map build {key} (after a Run)", took, ""))
        w4, w5 = found["W4"], found["W5"]
        last4 = flowmap.part_list(w4["c"])[-1]["label"]
        for entry, text in [("call", 'storage.is_json_object({"url": "/items/1"})'), ("get_item", "1500")]:
            took, d = timed(server.play, w4, last4, entry, text)
            rows.append((f"play W4 {entry} {text}", took, f"{len(d['events'])} steps" if isinstance(d, dict) else str(d)[:60]))
        took, d = timed(server.play, w5, "1", "call", "lab.main()", n=1)
        rows.append(("play W5 lab.main()", took, f"{len(d['events'])} steps" if isinstance(d, dict) else str(d)[:60]))
        commit = flowmap.part_list(w4["c"])[-1]["commit"]
        shutil.rmtree(os.path.join(home, "build", "harvest"), ignore_errors=True)
        t = time.perf_counter()
        calls = server.harvest(w4["c"], commit, log=lambda m: None)
        rows.append((f"harvest W4 Part {last4} (its tests once)", time.perf_counter() - t, f"{len(calls)} calls"))
        # a Run as you press it: the page asks, the server records, rebuilds the map and the page
        srv = server.serve(0, only=("W4",), suggest=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            def press():
                req = urllib.request.Request(f"http://127.0.0.1:{srv.server_port}/play", method="POST", headers={
                    "X-Flowmap-Token": srv.token, "Content-Type": "application/json"},
                    data=json.dumps({"key": "W4", "part": last4, "entry": "get_item", "input": "1500"}).encode())
                with urllib.request.urlopen(req, timeout=180) as r:
                    return json.load(r)
            took, _ = timed(press)
            rows.append(("Run pressed: W4 get_item 1500 (record + map + page)", took, ""))
        finally:
            srv.shutdown()
    finally:
        shutil.rmtree(home, ignore_errors=True)
    for name, took, note in rows:
        print(f"{took:7.2f} s  {name}{'  · ' + note if note else ''}")


def hook():
    """The tests map's rebuild (flowmap.py build --check, as the hook runs it), phase by phase."""
    spent, count = collections.defaultdict(float), collections.Counter()

    def wrap(name, f):
        def g(*a, **k):
            t = time.perf_counter()
            try:
                return f(*a, **k)
            finally:
                spent[name(a) if callable(name) else name] += time.perf_counter() - t
                count[name(a) if callable(name) else name] += 1
        return g

    run, sp = flowmap.run, subprocess.run
    flowmap.run = wrap(lambda a: os.path.basename(a[1]) if len(a) > 1 and a[1].endswith(".py") else os.path.basename(a[0]), run)
    flowmap.tool_tests = wrap("tool tests", flowmap.tool_tests)
    pickruns.pick = wrap("recording tests (pickruns)", pickruns.pick)
    subprocess.run = lambda cmd, *a, **k: (wrap("chrome page check", sp) if any("google-chrome" in str(x) for x in cmd) else sp)(cmd, *a, **k)
    try:
        t = time.perf_counter()
        flowmap.build(check=True, quiet=True, log=lambda m: None)
        total = time.perf_counter() - t
    finally:
        flowmap.run, subprocess.run = run, sp
    for k, v in sorted(spent.items(), key=lambda x: -x[1]):
        print(f"{v:7.2f} s  {k} ({count[k]}×)")
    print(f"{total:7.2f} s  tests map rebuild, total · check: {open(os.path.join(server.TESTS_MAP, 'build', 'check.txt')).readline().strip()}")


if __name__ == "__main__":
    playground()
    if "--hook" in sys.argv:
        hook()
