"""The flowmap playground: type an input on the page, press Run, and watch it travel START → END.

usage: python3 flowmap_playground/server.py [--port 8765]

It serves a page on this machine only (127.0.0.1). A run records your input with flowmap_tests' recorder on the code of
the Part you picked, through that Part's entry in the week's driver (drivers/w4.py, its PARTS table), with the same
safety as the tests: no network beyond this machine, no API keys, an empty folder (so no .env of yours is read),
90 seconds at most. The map, the recorder, the
scanner and the page all come from flowmap_tests; your runs and this page live here, in runs/ and build/ (not in git).
"""

import argparse
import importlib
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
lock = threading.Lock()  # one run at a time


def table(driver):
    """A driver's PARTS: per Part, its entries (label, hint) and its suggested inputs. Drivers import your project's
    code only inside their entries, so this Python (without the project's libraries) can read them."""
    sys.path.insert(0, os.path.dirname(driver))
    module = importlib.import_module(os.path.basename(driver)[:-3])
    return {part: {"entries": {name: {"label": e["label"], "hint": e.get("hint", "")} for name, e in block["entries"].items()},
                   "scenarios": [{"entry": s[0], "input": s[1], "kind": s[2], "about": s[3]} for s in block["scenarios"]]}
            for part, block in module.PARTS.items()}


def projects():
    """Every week in flowmap_tests/cfg that has a driver here."""
    os.chdir(TESTS_MAP)
    found = {}
    for cfg, c in flowmap.projects():
        driver = os.path.join(HERE, "drivers", c["KEY"].lower() + ".py")
        if os.path.exists(driver):
            found[c["KEY"]] = {"cfg": os.path.join(TESTS_MAP, cfg), "c": c, "driver": driver, "parts": table(driver)}
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


def page(all_projects, token):
    """The playground page: flowmap_tests' page with every week's map, your runs, and each Part's entries and suggested
    inputs. Returned for the server to keep: a second server writing build/ never changes the page this one serves."""
    os.chdir(TESTS_MAP)
    outs = [os.path.join(HERE, "build", f"proj_{k}.json") for k in all_projects]
    data = os.path.join(HERE, "build", "data.js")
    subprocess.run([sys.executable, "tools/combine.py", data, *outs], check=True)
    extra = {"token": token, "parts": {k: p["parts"] for k, p in all_projects.items()}}
    open(data, "a").write("window.PLAYGROUND = " + json.dumps(extra) + ";\n")
    out = os.path.join(HERE, "build", "playground.html")
    subprocess.run([sys.executable, "tools/inject.py", "page/flowmap.html", data, out], check=True, capture_output=True)
    return open(out, "rb").read()


def record(key, p, part, entry, text):
    """Your input through that Part's entry, recorded on that Part's code. Returns the run (as the page plays it) and
    the node of its hidden "you" frame."""
    os.chdir(TESTS_MAP)
    c = p["c"]
    chosen = next((x for x in flowmap.part_list(c) if x["label"] == part), None)
    if not chosen:
        raise ValueError(f"{key} has no Part {part}")
    export = os.path.abspath(flowmap.export(c["REPO"], chosen["commit"]))
    folder = os.path.join(HERE, "runs", key)
    os.makedirs(folder, exist_ok=True)
    name = time.strftime("%Y%m%d-%H%M%S") + f"-{entry}.json"
    out = os.path.join(folder, name)
    python = c.get("PYTHON") or os.path.join(c["REPO"], ".venv", "bin", "python")
    try:
        r = subprocess.run([python, os.path.join(TESTS_MAP, "tools", "trace.py"), export, f"play:{p['driver']}:{part}:{entry}", out, text],
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
    runs.append({"file": name, "key": "play_" + name[:-5], "part": part, "export": os.path.relpath(export, TESTS_MAP),
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
        self.reply(200, self.server.page, "text/html; charset=utf-8")

    def do_POST(self):
        if not self.local() or self.path != "/play" or self.headers.get("X-Flowmap-Token") != self.server.token:
            return self.reply(403, {"error": "only the playground's own page can ask for a run"})
        try:
            ask = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 10_000)))
            p = self.server.projects.get(ask.get("key"))
            part, text = str(ask.get("part", "")), str(ask.get("input", ""))
            if not p:
                raise ValueError("there is no playground for that week")
            if part not in p["parts"]:
                raise ValueError(f"Nothing to run at {part if part.startswith('W') else 'Part ' + part}")
            if ask.get("entry") not in p["parts"][part]["entries"]:
                raise ValueError(f"{ask.get('entry')} isn't in {part if part.startswith('W') else 'Part ' + part} yet")
            if not text.strip() or len(text) > 2000:
                raise ValueError("type something to run (at most 2,000 characters)")
            with lock:  # one run at a time
                run, nodes = record(ask["key"], p, part, ask["entry"], text)
                self.server.page = page(self.server.projects, self.server.token)
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
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.projects = found
    server.token = secrets.token_urlsafe(16)  # this server's secret: only its own page may ask for a run
    server.page = page(found, server.token)
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
