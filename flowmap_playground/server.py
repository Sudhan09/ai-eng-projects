"""The flowmap playground: type an input on the page, press Run, and watch it travel START → END.

usage: python3 flowmap_playground/server.py [--port 8765]
       python3 flowmap_playground/server.py --refresh     bring every week up to its newest commit, then stop
                                                           (flowmap_tests' update runs it after each commit)

It serves a page on this machine only (127.0.0.1). A run records your input with flowmap_tests' recorder on the code of
the Part you picked, through that Part's entry in the week's driver (drivers/w4.py, its PARTS table), with the same
safety as the tests: no network beyond this machine, no API keys, an empty folder (so no .env of yours is read),
90 seconds at most. The map, the recorder, the
scanner and the page all come from flowmap_tests; your runs and this page live here, in runs/ and build/ (not in git).

It follows your commits as the tests map does. After a commit (or on the first page load after it), your saved runs
are played again on their Part's new code, each Part's Try: suggestions are made again from its tests (suggest.py),
and the week's map is rebuilt. A Run pressed on a page from before the commit asks you to reload it first.
"""

import argparse
import concurrent.futures
import contextlib
import fcntl
import glob
import hashlib
import importlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS_MAP = os.path.join(os.path.dirname(HERE), "flowmap_tests")
sys.path.insert(0, os.path.join(TESTS_MAP, "tools"))
import flowmap  # noqa: E402  (flowmap_tests/tools: settings, Parts, exports)
import pickruns  # noqa: E402  (the recording environment and the length cap)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import suggest  # noqa: E402

KEEP = 20  # runs kept per week
HARVEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "harvest.py")
lock = threading.Lock()  # one run at a time
STALE = "Your code changed (a new commit) since this page loaded: reload the page"


def say(message):
    print(time.strftime("%H:%M:%S"), message, flush=True)


def driver_module(driver):
    """The driver as it is on disk now (an edit since the last load counts)."""
    folder = os.path.dirname(driver)
    for name, module in list(sys.modules.items()):
        if (getattr(module, "__file__", None) or "").startswith(folder + os.sep):
            del sys.modules[name]
    if folder in sys.path:
        sys.path.remove(folder)
    sys.path.insert(0, folder)
    return importlib.import_module(os.path.basename(driver)[:-3])


def table(driver):
    """A driver's PARTS: per Part, its entries (label, hint) and its suggested inputs. Drivers import your project's
    code only inside their entries, so this Python (without the project's libraries) can read them."""
    module = driver_module(driver)
    return {part: {"entries": {name: {"label": e["label"], "hint": e.get("hint", "")} for name, e in block["entries"].items()},
                   "scenarios": [{"entry": s[0], "input": s[1], "kind": s[2], "about": s[3]} for s in block["scenarios"]]}
            for part, block in module.PARTS.items()}


def projects(only=None):
    """Every week in flowmap_tests/cfg that has a driver here (or only those named)."""
    os.chdir(TESTS_MAP)
    found = {}
    for cfg, c in flowmap.projects():
        driver = os.path.join(HERE, "drivers", c["KEY"].lower() + ".py")
        if os.path.exists(driver) and (not only or c["KEY"] in only):
            found[c["KEY"]] = {"cfg": os.path.join(TESTS_MAP, cfg), "c": c, "driver": driver, "parts": table(driver)}
    return found


@contextlib.contextmanager
def build_lock():
    """One writer of runs/ and build/ at a time: this server, another one, or the refresh after a commit."""
    os.makedirs(os.path.join(HERE, "build"), exist_ok=True)
    with open(os.path.join(HERE, "build", ".lock"), "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def code_copy(c, commit):
    """flowmap_tests/exports/<commit>, made again from git when the tests map has deleted it (it keeps only the copies
    its Parts use). None when the commit is gone from git."""
    os.chdir(TESTS_MAP)
    try:
        return flowmap.export(c["REPO"], commit)
    except subprocess.CalledProcessError:
        shutil.rmtree(os.path.join(TESTS_MAP, "exports", commit), ignore_errors=True)  # export() made the folder first
        return None


def saved_runs(key):
    path = os.path.join(HERE, "runs", key, "index.json")
    return json.load(open(path)) if os.path.exists(path) else []


def save_runs(key, runs):
    json.dump(runs, open(os.path.join(HERE, "runs", key, "index.json"), "w"), indent=1, ensure_ascii=False)


def build(key, p, log=say):
    """That week's map from flowmap_tests, plus your runs, into build/proj_<key>.json."""
    os.chdir(TESTS_MAP)
    c = p["c"]
    for part in flowmap.part_list(c):
        flowmap.export(c["REPO"], part["commit"])
    runs = saved_runs(key)
    keep = [r for r in runs if code_copy(c, r["export"].split("/")[-1])]
    for r in runs:
        if r not in keep:
            log(f"{key}: your run {r['title']!r} is dropped: its commit {r['export'].split('/')[-1]} is gone from git")
            with contextlib.suppress(OSError):
                os.remove(os.path.join(HERE, "runs", key, r["file"]))
    if keep != runs:
        save_runs(key, keep)
    out = os.path.join(HERE, "build", f"proj_{key}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    r = subprocess.run([sys.executable, "tools/build_project.py", c["REPO"], "runs", out, p["cfg"], os.path.join(HERE, "runs", key)],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"building the {key} map failed: " + (r.stderr.strip().splitlines() or ["?"])[-1])
    return out


def row(p, part):
    """The driver's row a Part runs with: its own, or (a new Part nobody wrote a row for yet) the nearest one before
    it, so a new Part has entries and suggestions from its first commit. None when no row comes before it."""
    if part in p["parts"]:
        return part
    labels = [x["label"] for x in flowmap.part_list(p["c"])]
    earlier = [label for label in labels[: labels.index(part)] if label in p["parts"]] if part in labels else []
    return earlier[-1] if earlier else None


def rows(p):
    """Every Part's row, a new Part's borrowed from the Part before it."""
    out = {}
    for x in flowmap.part_list(p["c"]):
        if row(p, x["label"]):
            out[x["label"]] = p["parts"][row(p, x["label"])]
    return out


def with_suggestions(parts, made):
    """Each Part's Try: list: the ones made from its tests, or the driver's own when its tests gave none."""
    return {part: {**block, "scenarios": made.get(part) or block["scenarios"]} for part, block in parts.items()}


def page(all_projects, token):
    """The playground page: flowmap_tests' page with every week's map, your runs, and each Part's entries and suggested
    inputs. Returned for the server to keep: a second server writing build/ never changes the page this one serves."""
    os.chdir(TESTS_MAP)
    outs = [os.path.join(HERE, "build", f"proj_{k}.json") for k in all_projects]
    data = os.path.join(HERE, "build", "data.js")
    subprocess.run([sys.executable, "tools/combine.py", data, *outs], check=True)
    parts = {}
    for k, p in all_projects.items():
        try:
            made = {part: v["scenarios"] for part, v in json.load(open(os.path.join(HERE, "build", f"suggest_{k}.json"))).items()}
        except (OSError, ValueError):
            made = {}
        parts[k] = with_suggestions(rows(p), made)
    extra = {"token": token, "parts": parts}
    open(data, "a").write("window.PLAYGROUND = " + json.dumps(extra) + ";\n")
    out = os.path.join(HERE, "build", "playground.html")
    subprocess.run([sys.executable, "tools/inject.py", "page/flowmap.html", data, out], check=True, capture_output=True)
    return open(out, "rb").read()


def play(p, part, entry, text, out=None):
    """Your input through that Part's entry, recorded on that Part's code. Returns the recording, with "export": the
    code it ran on. A ValueError says why there's none. The recording is kept at `out` if given."""
    os.chdir(TESTS_MAP)
    c = p["c"]
    chosen = next((x for x in flowmap.part_list(c) if x["label"] == part), None)
    if not chosen:
        raise ValueError(f"{c['KEY']} has no Part {part}")
    if entry not in p["parts"].get(row(p, part), {}).get("entries", {}):
        raise ValueError(f"{entry} isn't in {part if part.startswith('W') else 'Part ' + part}")
    export = code_copy(c, chosen["commit"])
    if not export:
        raise ValueError(f"Part {part}'s commit {chosen['commit']} is gone from git")
    keep = out is not None
    if not keep:
        fd, out = tempfile.mkstemp(prefix="flowmap-try-", suffix=".json")
        os.close(fd)
        os.remove(out)
    python = c.get("PYTHON") or os.path.join(c["REPO"], ".venv", "bin", "python")
    try:
        r = subprocess.run([python, os.path.join(TESTS_MAP, "tools", "trace.py"), os.path.abspath(export), f"play:{p['driver']}:{row(p, part)}:{entry}", out, text],
                           capture_output=True, text=True, timeout=90, env=pickruns.safe_env())
    except subprocess.TimeoutExpired:
        raise ValueError("it ran for over 90 seconds; try a smaller input")
    if not os.path.exists(out):
        raise ValueError("the recorder crashed: " + ((r.stderr.strip().splitlines() or ["no message"])[-1])[:200])
    d = json.load(open(out))
    yours = [e for e in d["events"] if e["k"] in ("call", "new") and not e["fn"].startswith("test_playground.")]
    if not keep or len(d["events"]) > pickruns.MAX_EVENTS or not yours:
        os.remove(out)
    if not yours:
        raise ValueError(d["status"].removeprefix("raised ValueError: ") if d["status"] != "passed" else "your code never ran")
    if len(d["events"]) > pickruns.MAX_EVENTS:
        raise ValueError(f"too long to step through ({len(d['events'])} events); try a smaller input")
    d["export"] = f"exports/{chosen['commit']}"
    return d


def record(key, p, part, entry, text):
    """Your input through that Part's entry, recorded on that Part's code. Returns the run (as the page plays it) and
    the node of its hidden "you" frame."""
    folder = os.path.join(HERE, "runs", key)
    os.makedirs(folder, exist_ok=True)
    name = time.strftime("%Y%m%d-%H%M%S") + f"-{entry}.json"
    d = play(p, part, entry, text, os.path.join(folder, name))
    runs = saved_runs(key)
    title = " ⏎ ".join(line.strip() for line in text.splitlines() if line.strip())
    runs.append({"file": name, "key": "play_" + name[:-5], "part": part, "export": d["export"],
                 "title": title if len(title) <= 60 else title[:59] + "…", "entry": entry, "input": text})
    for old in runs[:-KEEP]:
        if os.path.exists(os.path.join(folder, old["file"])):
            os.remove(os.path.join(folder, old["file"]))
    save_runs(key, runs[-KEEP:])
    data = json.load(open(build(key, p)))
    you = {k: v for k, v in data["nodes"].items() if k.startswith("test_playground.")}  # the page may not know this entry yet
    return data["play"][-1], you


def follow(key, p, log=say):
    """Your saved runs, played again (the same entry, the same input) on their Part's newest code, as the tests map
    records its tests again after a commit. A run that can't run there any more stays on the code it was recorded on."""
    os.chdir(TESTS_MAP)
    commits = {x["label"]: x["commit"] for x in flowmap.part_list(p["c"])}
    runs, moved = saved_runs(key), 0
    for r in runs:
        now = commits.get(r["part"])
        if not now or r["export"] == f"exports/{now}":
            continue
        out = os.path.join(HERE, "runs", key, r["file"])
        try:
            play(p, r["part"], r["entry"], r["input"], out + ".new")
        except ValueError as exc:
            log(f"{key} Part {r['part']}: your run {r['title']!r} stays on {r['export'].split('/')[-1]} ({exc})")
            continue
        os.replace(out + ".new", out)
        r["export"] = f"exports/{now}"
        moved += 1
    if moved:
        save_runs(key, runs)
        log(f"{key}: {moved} of your runs played again on the new code")


def harvest(c, commit, log=say):
    """What the tests at `commit` passed into your code (harvest.py), kept in build/harvest/ per commit."""
    stamp = hashlib.md5(open(HARVEST, "rb").read()).hexdigest()[:8]
    out = os.path.join(HERE, "build", "harvest", f"{commit}_{stamp}.json")
    if not os.path.exists(out):
        export = code_copy(c, commit)
        if not export:
            return []
        os.makedirs(os.path.dirname(out), exist_ok=True)
        python = c.get("PYTHON") or os.path.join(c["REPO"], ".venv", "bin", "python")
        try:
            r = subprocess.run([python, HARVEST, os.path.join(TESTS_MAP, export), out + ".tmp"], capture_output=True, text=True,
                               timeout=600, env=pickruns.safe_env())
        except subprocess.TimeoutExpired:
            log(f"{c['KEY']}: your tests at {commit} took over 10 minutes; no suggestions from them")
            return []
        if not os.path.exists(out + ".tmp"):
            log(f"{c['KEY']}: reading your tests at {commit} failed: " + ((r.stderr.strip().splitlines() or ["?"])[-1])[:200])
            return []
        os.replace(out + ".tmp", out)
    return json.load(open(out))["calls"]


def fakes(c):
    """The week's test fakes, and their old names (W4's FlakyAPI was ChaosAPI in Week 3)."""
    found = c.get("FAKES", [])
    return [*found, *(old for old, new in c.get("ALIASES", {}).items() if new in found)]


def suggestions(key, p, log=say):
    """Each Part's Try: suggestions, made from its tests (suggest.py) and played on its code. Kept in
    build/suggest_<key>.json, and made again only for a Part whose commit (or the drivers) changed."""
    os.chdir(TESTS_MAP)
    c, driver = p["c"], driver_module(p["driver"])
    path = os.path.join(HERE, "build", f"suggest_{key}.json")
    try:
        saved = json.load(open(path))
    except (OSError, ValueError):
        saved = {}
    stamp = hashlib.md5(b"".join(open(f, "rb").read() for f in [*sorted(glob.glob(os.path.join(HERE, "drivers", "*.py"))),
                                                                  suggest.__file__, HARVEST])).hexdigest()[:8]
    parts, out, todo = flowmap.part_list(c), {}, []
    for i, part in enumerate(parts):
        if not row(p, part["label"]):
            continue
        prev = parts[i - 1]["commit"] if i else None
        mark = f"{part['commit']}:{prev}:{row(p, part['label'])}:{stamp}"
        if saved.get(part["label"], {}).get("mark") == mark:
            out[part["label"]] = saved[part["label"]]
        else:
            todo.append((part["label"], part["commit"], prev, mark))
    if todo:
        commits = sorted({x for t in todo for x in t[1:3] if x})
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            calls = dict(zip(commits, pool.map(lambda x: harvest(c, x, log), commits)))
        private = [os.path.expanduser("~"), tempfile.gettempdir() + os.sep, TESTS_MAP]  # this machine's folders
        tries = {label: suggest.candidates(driver.PARTS[row(p, label)], calls[commit], calls[prev] if prev else [],
                                                fakes(c), private)
                 for label, commit, prev, _ in todo}

        def attempt(label, candidate):
            try:
                return play(p, label, candidate[0], candidate[1])
            except ValueError:
                return None

        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            runs = {(label, t): pool.submit(attempt, label, t) for label, ts in tries.items() for t in ts}
        for label, commit, prev, mark in todo:
            picked = suggest.choose([(t, runs[(label, t)].result()) for t in tries[label]])
            out[label] = {"mark": mark, "scenarios": picked}
            log(f"{key} Part {label}: {len(picked)} suggestion{'s' if len(picked) != 1 else ''} from your tests" if picked else
                f"{key} Part {label}: no suggestions from your tests; the driver's own are shown")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(out, open(path, "w"), indent=1, ensure_ascii=False)
    return {label: v["scenarios"] for label, v in out.items()}


def signature(key, p):
    """What a week's playground is made from: its Parts' commits, the tests map's build of the week, the drivers and
    the playground's own code. A new commit (or a new tests map, or a driver edit) changes it."""
    os.chdir(TESTS_MAP)
    h = hashlib.md5(json.dumps([x["label"] + ":" + x["commit"] for x in flowmap.part_list(p["c"])]).encode())
    for f in [os.path.join(TESTS_MAP, "build", f"proj_{key}.json"), *sorted(glob.glob(os.path.join(HERE, "drivers", "*.py"))),
              os.path.abspath(__file__), suggest.__file__, HARVEST]:
        with contextlib.suppress(OSError):
            h.update(open(f, "rb").read())
    return h.hexdigest()


def refresh(found, log=say, suggest=True):
    """Bring each week up to its newest commit: your saved runs follow their Part's code, the Parts' suggestions are made
    from their tests, the map is rebuilt. A week that hasn't changed since its last refresh is skipped.
    Returns {week: its signature}."""
    built = {}
    with build_lock():
        for key, p in found.items():
            sig = signature(key, p)
            stamp = os.path.join(HERE, "build", f"stamp_{key}.txt")
            proj, index = os.path.join(HERE, "build", f"proj_{key}.json"), os.path.join(HERE, "runs", key, "index.json")
            fresh = os.path.exists(proj) and os.path.getmtime(proj) >= (os.path.getmtime(index) if os.path.exists(index) else 0)
            if not (suggest and fresh and os.path.exists(stamp) and open(stamp).read() == sig):
                follow(key, p, log)
                if suggest:
                    suggestions(key, p, log)
                build(key, p, log)
                if suggest:
                    open(stamp, "w").write(sig)
            built[key] = sig
    return built


def current(server):
    """The page as of your newest commit: refreshed (once) when a week changed since this server built it."""
    found = projects(server.only)
    if {k: signature(k, p) for k, p in found.items()} != server.built:
        say("your code changed: updating the playground")
        server.built = refresh(found, suggest=server.suggest)
        server.projects = found
        server.page = page(found, server.token)
        say("the playground is up to date")


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
        with lock:
            current(self.server)
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
            if not row(p, part):
                raise ValueError(f"Nothing to run at {part if part.startswith('W') else 'Part ' + part}")
            if ask.get("entry") not in p["parts"][row(p, part)]["entries"]:
                raise ValueError(f"{ask.get('entry')} isn't in {part if part.startswith('W') else 'Part ' + part} yet")
            if not text.strip() or len(text) > 2000:
                raise ValueError("type something to run (at most 2,000 characters)")
            with lock:  # one run at a time
                if signature(ask["key"], p) != self.server.built.get(ask["key"]):
                    return self.reply(409, {"error": STALE})
                with build_lock():
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


class Server(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return  # the browser left (a reload, a closed tab): nothing to report
        super().handle_error(request, client_address)


def serve(port=8765, only=None, suggest=True):
    os.makedirs(os.path.join(HERE, "build"), exist_ok=True)
    found = projects(only)
    built = refresh(found, suggest=suggest)
    server = Server(("127.0.0.1", port), Handler)
    server.projects, server.only, server.suggest, server.built = found, only, suggest, built
    server.token = secrets.token_urlsafe(16)  # this server's secret: only its own page may ask for a run
    server.page = page(found, server.token)
    return server


def main():
    ap = argparse.ArgumentParser(description="type an input, watch it travel START → END")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--refresh", action="store_true", help="bring every week up to its newest commit, then stop")
    a = ap.parse_args()
    if not shutil.which("git"):
        raise SystemExit("needs git")
    if a.refresh:
        found = projects()
        refresh(found)
        print(f"playground up to date ({', '.join(found)})", flush=True)
        return
    server = serve(a.port)
    print(f"flowmap playground: http://127.0.0.1:{a.port}/  ({', '.join(server.projects)}; Ctrl+C stops it)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
