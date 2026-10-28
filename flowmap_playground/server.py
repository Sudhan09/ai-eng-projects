"""The flowmap playground: type an input on the page, press Run, and watch it travel START → END.

usage: python3 flowmap_playground/server.py [--port 8765]

It serves a page on this machine only (127.0.0.1). A run records your input with flowmap_tests' recorder on the newest
Part's code, through the week's driver (drivers/w4.py), with the same safety as the tests: no network beyond this
machine, no API keys, an empty folder (so no .env of yours is read), 90 seconds at most. The map, the recorder, the
scanner and the page all come from flowmap_tests; your runs and this page live here, in runs/ and build/ (not in git).
"""

import argparse
import ast
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS_MAP = os.path.join(os.path.dirname(HERE), "flowmap_tests")
sys.path.insert(0, os.path.join(TESTS_MAP, "tools"))
import flowmap  # noqa: E402  (flowmap_tests/tools: settings, Parts, exports)
import pickruns  # noqa: E402  (the recording environment and the length cap)

KEEP = 20  # runs kept per week
TOKEN = secrets.token_urlsafe(16)  # this start's secret: only this page may ask for a run
lock = threading.Lock()


def entries(driver):
    """A driver's ENTRIES, read without running it (the server's Python doesn't have the project's libraries)."""
    tree = ast.parse(open(driver).read())
    node = next(n.value for n in tree.body if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "ENTRIES" for t in n.targets))
    out = {}
    for k, v in zip(node.keys, node.values):
        fields = {fk.value: fv.value for fk, fv in zip(v.keys, v.values) if isinstance(fv, ast.Constant)}
        out[k.value] = {"label": fields.get("label", k.value), "hint": fields.get("hint", "")}
    return out


def projects():
    """Every week in flowmap_tests/cfg that has a driver here."""
    os.chdir(TESTS_MAP)
    found = {}
    for cfg, c in flowmap.projects():
        driver = os.path.join(HERE, "drivers", c["KEY"].lower() + ".py")
        if os.path.exists(driver):
            found[c["KEY"]] = {"cfg": os.path.join(TESTS_MAP, cfg), "c": c, "driver": driver, "entries": entries(driver)}
    return found


def build(key, p):
    """That week's map from flowmap_tests, plus your runs, into build/proj_<key>.json."""
    os.chdir(TESTS_MAP)
    c = p["c"]
    for part in flowmap.part_list(c):
        flowmap.export(c["REPO"], part["commit"])
    out = os.path.join(HERE, "build", f"proj_{key}.json")
    r = subprocess.run([sys.executable, "tools/build_project.py", c["REPO"], "runs", out, p["cfg"], os.path.join(HERE, "runs", key)],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"building the {key} map failed: " + (r.stderr.strip().splitlines() or ["?"])[-1])
    return out


def page(all_projects):
    """The playground page: flowmap_tests' page with every week's map, your runs and the entries to type into."""
    os.chdir(TESTS_MAP)
    outs = [os.path.join(HERE, "build", f"proj_{k}.json") for k in all_projects]
    data = os.path.join(HERE, "build", "data.js")
    subprocess.run([sys.executable, "tools/combine.py", data, *outs], check=True)
    extra = {"token": TOKEN, "entries": {k: p["entries"] for k, p in all_projects.items()}}
    open(data, "a").write("window.PLAYGROUND = " + json.dumps(extra) + ";\n")
    subprocess.run([sys.executable, "tools/inject.py", "page/flowmap.html", data, os.path.join(HERE, "build", "playground.html")], check=True)


def record(key, p, entry, text):
    """Your input through the driver's entry, recorded on the newest Part's code. Returns the run (as the page plays it)
    and the node of its hidden "you" frame."""
    os.chdir(TESTS_MAP)
    c = p["c"]
    newest = flowmap.part_list(c)[-1]
    export = os.path.abspath(flowmap.export(c["REPO"], newest["commit"]))
    folder = os.path.join(HERE, "runs", key)
    os.makedirs(folder, exist_ok=True)
    name = time.strftime("%Y%m%d-%H%M%S") + f"-{entry}.json"
    out = os.path.join(folder, name)
    python = c.get("PYTHON") or os.path.join(c["REPO"], ".venv", "bin", "python")
    try:
        r = subprocess.run([python, os.path.join(TESTS_MAP, "tools", "trace.py"), export, f"play:{p['driver']}:{entry}", out, text],
                           capture_output=True, text=True, timeout=90, env=pickruns.safe_env())
    except subprocess.TimeoutExpired:
        raise ValueError("it ran for over 90 seconds; try a smaller input")
    if not os.path.exists(out):
        raise ValueError("the recorder crashed: " + ((r.stderr.strip().splitlines() or ["no message"])[-1])[:200])
    d = json.load(open(out))
    yours = [e for e in d["events"] if e["k"] in ("call", "new") and not e["fn"].startswith("test_playground.")]
    if len(d["events"]) > pickruns.MAX_EVENTS or not yours:
        os.remove(out)
        if not yours:
            raise ValueError(d["status"].removeprefix("raised ValueError: ") if d["status"] != "passed" else "your code never ran")
        raise ValueError(f"too long to step through ({len(d['events'])} events); try a smaller input")
    index = os.path.join(folder, "index.json")
    runs = json.load(open(index)) if os.path.exists(index) else []
    title = " ⏎ ".join(line.strip() for line in text.splitlines() if line.strip())
    runs.append({"file": name, "key": "play_" + name[:-5], "part": newest["label"], "export": os.path.relpath(export, TESTS_MAP),
                 "title": title if len(title) <= 60 else title[:59] + "…", "entry": entry, "input": text})
    for old in runs[:-KEEP]:
        if os.path.exists(os.path.join(folder, old["file"])):
            os.remove(os.path.join(folder, old["file"]))
    json.dump(runs[-KEEP:], open(index, "w"), indent=1, ensure_ascii=False)
    data = json.load(open(build(key, p)))
    you = {k: v for k, v in data["nodes"].items() if k.startswith("test_playground.")}  # the page may not know this entry yet
    return data["play"][-1], you


class Handler(BaseHTTPRequestHandler):
    def local(self):
        """A request for this server by its own name: a web page can't reach it through a borrowed name."""
        return self.headers.get("Host", "") in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")

    def reply(self, status, body, kind="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self.local():
            return self.reply(403, {"error": "not this server's name"})
        if self.path.split("?")[0] not in ("/", "/index.html"):
            return self.reply(404, {"error": "not found"})
        self.reply(200, open(os.path.join(HERE, "build", "playground.html"), "rb").read(), "text/html; charset=utf-8")

    def do_POST(self):
        if not self.local() or self.path != "/play" or self.headers.get("X-Flowmap-Token") != TOKEN:
            return self.reply(403, {"error": "only the playground's own page can ask for a run"})
        try:
            ask = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 10_000)))
            p = self.server.projects.get(ask.get("key"))
            text = str(ask.get("input", ""))
            if not p or ask.get("entry") not in p["entries"]:
                raise ValueError("there is no playground for that week or entry")
            if not text.strip() or len(text) > 2000:
                raise ValueError("type something to run (at most 2,000 characters)")
            with lock:  # one run at a time
                run, nodes = record(ask["key"], p, ask["entry"], text)
                page(self.server.projects)
            self.reply(200, {"run": run, "nodes": nodes})
        except ValueError as exc:
            self.reply(400, {"error": str(exc)})
        except Exception as exc:  # a bug here: say so on the page instead of hanging
            self.reply(500, {"error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, fmt, *args):  # quiet: one line per run instead of one per request
        if self.command == "POST":
            sys.stderr.write(time.strftime("%H:%M:%S ") + (fmt % args) + "\n")


def serve(port=8765):
    os.makedirs(os.path.join(HERE, "build"), exist_ok=True)
    found = projects()
    for key, p in found.items():
        build(key, p)
    page(found)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.projects = found
    return server


def main():
    ap = argparse.ArgumentParser(description="type an input, watch it travel START → END")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    if not shutil.which("git"):
        raise SystemExit("needs git")
    server = serve(a.port)
    print(f"flowmap playground: http://127.0.0.1:{a.port}/  ({', '.join(server.projects)}; Ctrl+C stops it)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
