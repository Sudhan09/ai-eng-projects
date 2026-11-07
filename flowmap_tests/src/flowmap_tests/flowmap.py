"""flowmap: keep the project map in step with the code.

usage (from anywhere):
  python3 flowmap_tests/src/flowmap_tests/flowmap.py build [--check]     rebuild the map; record runs for Parts that need them
  python3 flowmap_tests/src/flowmap_tests/flowmap.py update              what the git hook runs in the background: build and check, quietly,
                                                       then bring the playground (flowmap_playground/) up to the same commit
  python3 flowmap_tests/src/flowmap_tests/flowmap.py note                the one line the hook prints after a commit (fast)
  python3 flowmap_tests/src/flowmap_tests/flowmap.py hook <project>      install the git hook in that project's repo (e.g. W4)
  python3 flowmap_tests/src/flowmap_tests/flowmap.py init <key> <repo> --week N [--practical FILE] [--name NAME]
                                                       start a map for another project, and install its git hook

Every project is a settings file in cfg/. The map is build/flowmap.html: open it in a browser, and refresh it after
an update.
"""

import argparse
import contextlib
import fcntl
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))  # flowmap_tests/, above src/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gitparts  # noqa: E402
import pickruns  # noqa: E402

PAGE = "build/flowmap.html"


WORKSPACE = os.path.dirname(ROOT)


def load(cfg):
    c = {}
    exec(open(cfg).read(), c)
    for k in ("REPO", "PRACTICAL"):  # paths in cfg/ are relative to the workspace, so a copied workspace still works
        if c.get(k):
            c[k] = os.path.join(WORKSPACE, c[k])
    return c


def projects():
    return [(p, load(p)) for p in sorted(glob.glob("cfg/*.py"))]


def run(*cmd, quiet=False):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"failed: {' '.join(cmd)}\n{r.stdout[-2000:]}{r.stderr[-2000:]}")
    if not quiet and r.stdout.strip():
        print(r.stdout.strip())
    return r.stdout


def export(repo, commit):
    """A read-only copy of one commit (git archive never touches the repo's working tree)."""
    path = f"exports/{commit}"
    if not os.path.isdir(path):
        os.makedirs(path)
        archive = subprocess.run(["git", "-C", repo, "archive", commit], capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", path], input=archive, check=True)
    return path


def part_list(c):
    if "PARTS" in c:
        return [{"commit": a, "label": b, "title": t, "inProgress": False} for a, b, t in c["PARTS"]]
    ps, _, base = gitparts.parts(c["REPO"], c["WEEK_NUM"], c.get("PRACTICAL"))
    return ([base] if base else []) + ps


def build(check=False, quiet=False, log=print, accept=False):
    os.chdir(ROOT)
    os.makedirs("build", exist_ok=True)
    outs, norun, notes, used = [], [], [], set()
    for cfg, c in projects():
        key, repo = c["KEY"], c["REPO"]
        python = c.get("PYTHON") or os.path.join(repo, ".venv", "bin", "python")
        ps = part_list(c)
        for p in ps:
            used.add(export(repo, p["commit"]))
        for _, meta in c.get("RUN_META", []):
            if meta.get("export"):
                used.add(export(repo, meta["export"].split("/")[-1]))
        run(sys.executable, "src/flowmap_tests/conds.py", f"exports/{ps[-1]['commit']}", f"build/conds_{key}.json", *c.get("CODE_DIRS", []), quiet=True)
        # Parts with no runs of their own get the tests they added, recorded on their own code
        have = {m["part"] for _, m in c.get("RUN_META", [])}
        for i, p in enumerate(ps):
            if p["label"] in have or p.get("base"):  # "where Week 3 ended" is the week before: it has its own runs
                continue
            prev = f"exports/{ps[i - 1]['commit']}" if i else None
            got = pickruns.pick(key, p["label"], p["commit"], f"exports/{p['commit']}", prev, python, log=log, code_dirs=c.get("CODE_DIRS", []))
            if not got["picked"]:  # say why, so a Part never goes quiet without a reason
                why = sorted({w for _, w in got.get("skipped", [])}) or [f"no reason saved; delete runs/auto/{key}/{p['label']} to check again"]
                # the test's own fault is a note; the recorder failing (a crash, a failed test, no reason) is a problem
                fine = all(re.match(r"touches only|too long|skipped|the Part added no", w) for w in why)
                (notes if fine else norun).append(f"{key} Part {p['label']}: no run ({'; '.join(why)})")
        out = f"build/proj_{key}.json"
        run(sys.executable, "src/flowmap_tests/build_project.py", repo, "runs", out, cfg, quiet=quiet)
        outs.append(out)
    run(sys.executable, "src/flowmap_tests/combine.py", "build/data_all.js", *outs, quiet=True)
    run(sys.executable, "src/flowmap_tests/inject.py", "page/flowmap.html", "build/data_all.js", PAGE, quiet=True)
    run("node", "--check", PAGE + ".app.js", quiet=True)
    for old in glob.glob("exports/*"):  # copies of commits no Part uses any more (a Part redone, a branch dropped)
        if old not in used:
            shutil.rmtree(old)
            # and what was kept for it: its compiled files (build/pyc/, by full path) and its scan (build/scan/)
            shutil.rmtree(os.path.join("build", "pyc", os.path.abspath(old).lstrip(os.sep)), ignore_errors=True)
            for kept in glob.glob(f"build/scan/{os.path.basename(old)}_*.json"):
                os.remove(kept)
    tmp = tempfile.gettempdir()  # compiled files of throwaway copies (the tool tests' sample projects) that are gone
    for kept in glob.glob(os.path.join("build", "pyc", tmp.lstrip(os.sep), "*")):
        if not os.path.exists(os.path.join(tmp, os.path.basename(kept))):
            shutil.rmtree(kept, ignore_errors=True)
    state = {c["KEY"]: [p["label"] + ":" + p["commit"] for p in part_list(c)] for _, c in projects()}
    json.dump(state, open("build/state.json", "w"))
    if check:
        text, summary = page_check(outs)
        print(text)
        found = problems(text) + norun
        if summary is not None:
            json.dump(summary, open("build/summary.json", "w"), indent=1, ensure_ascii=False)
            found += compare(summary, accept)
        found += tool_tests()
        open("build/check.txt", "w").write((f"{len(found)} problems\n" + "\n".join(found) + "\n" if found else "ok\n")
                                           + "".join(f"note: {n}\n" for n in notes))
    return state


CHECK_CODE = ["page/flowmap.html", "checks/smoke.js", "src/flowmap_tests/inject.py", "src/flowmap_tests/combine.py"]


def page_check(outs):
    """The browser check (checks/smoke.js) on the weeks whose map changed since their last clean check; a week that
    hasn't changed keeps its result (build/check_cache.json). A change to the page or the check itself checks every week.
    Returns (the check's text, every week's summary), as one full check would."""
    import html
    page = hashlib.md5(b"".join(open(f, "rb").read() for f in CHECK_CODE)).hexdigest()
    try:
        cache = json.load(open("build/check_cache.json"))
    except (OSError, ValueError):
        cache = {}
    if cache.get("page") != page:
        cache = {"page": page, "weeks": {}}
    sig = {out: hashlib.md5(open(out, "rb").read()).hexdigest() for out in outs}
    key_of = {out: json.load(open(out))["key"] for out in outs}
    todo = [out for out in outs if cache["weeks"].get(key_of[out], {}).get("sig") != sig[out]]
    fresh, header, extra, summary = {}, "SMOKE OK", [], {}
    if todo:
        run(sys.executable, "src/flowmap_tests/combine.py", "build/data_check.js", *todo, quiet=True)
        run(sys.executable, "src/flowmap_tests/inject.py", "page/flowmap.html", "build/data_check.js", "build/check.html", "--hook", "checks/smoke.js", quiet=True)
        dom = subprocess.run(["timeout", "600", "google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--window-size=1440,900",
                              "--virtual-time-budget=2500000", "--dump-dom", f"file://{ROOT}/build/check.html"], capture_output=True, text=True).stdout
        for f in ("build/check.html", "build/check.html.app.js", "build/data_check.js"):
            with contextlib.suppress(OSError):
                os.remove(f)
        m = re.search(r'<pre id="smoke">(.*?)</pre>', dom, re.S)
        if not m:
            return "CHECK FAILED: no result", None
        lines = html.unescape(m.group(1)).splitlines()
        header, keys = lines[0], [key_of[out] for out in todo]
        fresh, extra = by_week(lines[1:], keys)
        m = re.search(r'<pre id="summary">(.*?)</pre>', dom, re.S)
        summary = json.loads(html.unescape(m.group(1))) if m else None
        for out in todo:  # a week checked clean is kept; one with a problem is checked again next time
            key = key_of[out]
            if summary is not None and header == "SMOKE OK" and not problems("SMOKE OK\n" + "\n".join(fresh.get(key, []))):
                cache["weeks"][key] = {"sig": sig[out], "lines": fresh.get(key, []), "summary": summary.get(key, {})}
            else:
                cache["weeks"].pop(key, None)
        if header == "SMOKE OK" and not problems("\n".join([header, *extra])):
            cache["extra"] = [x for x in extra if not x.startswith(("ERROR ", "PROBLEM "))]  # the page as a whole
        json.dump(cache, open("build/check_cache.json", "w"))
    else:
        extra = cache.get("extra", [])
    checked = {key_of[out] for out in todo}
    body = [x for x in extra if x.startswith(("ERROR ", "PROBLEM "))]
    merged = None if summary is None else {}
    for key in (key_of[out] for out in outs):
        body += fresh.get(key, []) if key in checked else cache["weeks"][key]["lines"]
        if merged is not None and (key in summary if key in checked else True):
            merged[key] = summary[key] if key in checked else cache["weeks"][key]["summary"]
    body += [x for x in extra if not x.startswith(("ERROR ", "PROBLEM "))]
    return "\n".join([header, *body]), merged


def by_week(lines, keys):
    """A check's lines, each with its week ("W4 Part 2: ...", "PROBLEM W4 Part 2 ...", and the "   ▶" run lines under a
    Part's line), and the lines of no week (the page as a whole)."""
    weeks, rest, at = {}, [], None
    for line in lines:
        word = line.split(" ", 2)[1] if line.startswith(("PROBLEM ", "ERROR ")) and line.count(" ") >= 1 else line.split(" ", 1)[0]
        if word in keys:
            at = word
            weeks.setdefault(word, []).append(line)
        elif line.startswith("   ▶") and at:
            weeks[at].append(line)
        else:
            rest.append(line)
    return weeks, rest


def problems(text):
    """What the browser check found wrong: page errors, a guard that failed (START, END, steps, panels, words),
    words on top of each other, lines running through cards."""
    lines = text.splitlines()
    if not lines or not lines[0].startswith("SMOKE"):
        return ["the page did not load"]
    found = [l[len("ERROR "):] for l in lines if l.startswith("ERROR ")] + [l[len("PROBLEM "):] for l in lines if l.startswith("PROBLEM ")]
    if not lines[0].startswith("SMOKE OK") and not found:
        found.append("the page check failed")
    for line in lines:
        o, t = re.search(r"overlaps (\d+)", line), re.search(r"through cards (\d+)", line)
        if (o and int(o.group(1))) or (t and int(t.group(1))):
            found.append(line.split(";")[0] + (f"; {o.group(0)}" if o and int(o.group(1)) else "") + (f"; {t.group(0)}" if t and int(t.group(1)) else ""))
    return found


def compare(summary, accept=False):
    """An old week must not change by itself: a Part whose commit is the same as in the saved summary
    (build/expected.json) must look the same. A Part with a new commit, or a new Part, is simply saved."""
    path = "build/expected.json"
    try:
        expected = json.load(open(path))
    except (OSError, ValueError):
        expected = {}
    found, keep = [], {k: dict(v) for k, v in expected.items()}
    for key, parts in summary.items():
        for label, now in parts.items():
            was = expected.get(key, {}).get(label)
            if was and was.get("commit") == now.get("commit") and was != now and not accept:
                found.append(f"{key} Part {label} changed by itself: {difference(was, now)} (meant it? flowmap.py build --accept)")
            else:
                keep.setdefault(key, {})[label] = now
    for key, parts in expected.items():
        for label in parts:
            if label not in summary.get(key, {}) and not accept:
                found.append(f"{key} Part {label} is gone from the map (meant it? flowmap.py build --accept)")
    json.dump(summary if accept else keep, open(path, "w"), indent=1, ensure_ascii=False)
    return found


def difference(was, now):
    out = [f"{k} {was.get(k)} → {now.get(k)}" for k in ("cards", "lines") if was.get(k) != now.get(k)]
    old, new = {r["title"]: r for r in was.get("runs", [])}, {r["title"]: r for r in now.get("runs", [])}
    for t in sorted(set(old) | set(new)):
        a, b = old.get(t), new.get(t)
        if a != b:
            what = "added" if not a else "gone" if not b else ", ".join(
                f"{k} {a.get(k)!r} → {b.get(k)!r}" if k != "calls" else f"calls {sorted(set(b[k]) - set(a[k]))} new, {sorted(set(a[k]) - set(b[k]))} gone"
                for k in ("start", "end", "steps", "calls") if a.get(k) != b.get(k))
            out.append(f'run "{t}" {what}')
    return "; ".join(out[:3])


def tool_tests():
    """flowmap's own tests (tests/), run again whenever the tools changed since they last passed."""
    if not os.path.isdir("tests"):
        return []
    files = sorted(glob.glob("src/flowmap_tests/*.py") + glob.glob("page/*") + glob.glob("checks/*.js") + glob.glob("tests/**/*.py", recursive=True))
    stamp = hashlib.md5(b"".join(open(f, "rb").read() for f in files)).hexdigest()
    try:
        if open("build/.tested").read() == stamp:
            return []
    except OSError:
        pass
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], capture_output=True, text=True)
    if r.returncode:
        failed = [l for l in r.stderr.splitlines() if l.startswith(("FAIL:", "ERROR:"))]
        return [f"tool test {l}" for l in failed[:5]] or ["tool tests failed: " + (r.stderr.strip().splitlines() or ["?"])[-1]]
    open("build/.tested", "w").write(stamp)
    return []


def note():
    """One line about what the last commit changed for the map. Fast: reads git only."""
    os.chdir(ROOT)
    try:
        old = json.load(open("build/state.json"))
    except (OSError, ValueError):
        old = {}
    lines, behind = [], set()
    for _, c in projects():
        try:
            now = part_list(c)
        except subprocess.CalledProcessError:
            continue
        before = {x.split(":")[0]: x.split(":")[1] for x in old.get(c["KEY"], [])}
        head = subprocess.run(["git", "-C", c["REPO"], "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        for p in now:
            if p["label"] not in before:
                lines.append(f"{c['KEY']} Part {p['label']} added · {p['title']}")
            elif before[p["label"]] != p["commit"]:
                lines.append(f"{c['KEY']} Part {p['label']} updated")
            # a Part that changed in a commit before this one was never built: an earlier update didn't run
            if before.get(p["label"]) != p["commit"] and not head.startswith(p["commit"][:7]) and not p["commit"].startswith(head[:7]):
                behind.add(c["KEY"])
    try:
        last = open("build/check.txt").read().split("\n")[0]
    except OSError:
        last = ""
    checked = "" if not last else " · last check: ok" if last == "ok" else f" · last check: {last} (see flowmap_tests/build/check.txt)"
    late = f" · the map was behind for {', '.join(sorted(behind))} (an earlier update didn't run); this update catches up. If it keeps happening, run: python3 {ROOT}/src/flowmap_tests/flowmap.py update" if behind else ""
    print("flowmap: " + ("; ".join(lines) if lines else "no new Part") + f" · updating {PAGE} in the background" + checked + late)


def update():
    """Build with a lock; a commit made while a build runs gets one more build when it ends."""
    os.chdir(ROOT)
    os.makedirs("build", exist_ok=True)
    try:  # the hook appends to this log; keep its last 1,000 lines
        log = open("build/update.log").readlines()
        if len(log) > 1000:
            open("build/update.log", "w").writelines(log[-1000:])
    except OSError:
        pass
    with open("build/.lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            open("build/.again", "w").close()
            return
        while True:
            if os.path.exists("build/.again"):
                os.remove("build/.again")
            t0 = time.time()
            try:
                build(check=True, quiet=True, log=lambda m: print(time.strftime("%H:%M:%S"), m))
                print(time.strftime("%H:%M:%S"), f"map rebuilt in {time.time() - t0:.0f} s")
            except SystemExit as e:
                print(time.strftime("%H:%M:%S"), "update failed:", e)
            refresh_playground(log=lambda m: print(time.strftime("%H:%M:%S"), m))
            if not os.path.exists("build/.again"):
                break


def refresh_playground(log=print):
    """The playground (flowmap_playground/, next to this folder) follows the same commit: your saved inputs are played
    again on the new code and each Part's suggestions are made again from its tests. Its trouble never stops the map."""
    server = os.path.join(WORKSPACE, "flowmap_playground", "src", "flowmap_playground", "server.py")
    if not os.path.exists(server):
        return
    try:
        r = subprocess.run([sys.executable, server, "--refresh"], capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        return log("playground: its refresh took over 30 minutes and was stopped")
    for line in r.stdout.strip().splitlines():
        log("playground: " + line)
    if r.returncode:
        log("playground: refresh failed: " + (r.stderr.strip().splitlines() or ["?"])[-1])


HOOK = """#!/bin/sh
# flowmap: keep the project map up to date (installed by flowmap_tests/src/flowmap_tests/flowmap.py hook; delete this file to stop it)
python3 {root}/src/flowmap_tests/flowmap.py note
( cd {root} && nohup python3 src/flowmap_tests/flowmap.py update >> build/update.log 2>&1 & )
"""


def hook(key):
    """After a commit, and after a git pull that brings a Part merged on GitHub (post-merge)."""
    os.chdir(ROOT)
    c = next((c for _, c in projects() if c["KEY"] == key), None)
    if not c:
        raise SystemExit(f"no project {key} in cfg/")
    install_hooks(c["REPO"], ROOT)


def install_hooks(repo, root):
    """Our lines in the repo's hooks, pointing at this flowmap folder. Lines from an older flowmap folder (flowmap/ before
    it became flowmap_tests/) are replaced; any other lines the hook has stay."""
    ours = HOOK.format(root=root).split("\n", 1)[1]  # without the #!/bin/sh line
    for name in ("post-commit", "post-merge"):
        path = os.path.join(repo, ".git", "hooks", name)
        old = open(path).read() if os.path.exists(path) else ""
        if ours in old:
            print(f"already installed: {path}")
            continue
        keep = [line for line in (old or "#!/bin/sh").splitlines() if not (line.startswith("# flowmap:") or "flowmap.py note" in line or "flowmap.py update" in line)]
        open(path, "w").write("\n".join(keep).rstrip("\n") + "\n" + ours)
        os.chmod(path, 0o755)
        print(f"{'updated (it pointed at another flowmap folder)' if 'flowmap.py note' in old else 'installed'}: {path}")


def init(key, repo, week, practical, name):
    os.chdir(ROOT)
    path = f"cfg/{key.lower()}.py"
    if os.path.exists(path):
        raise SystemExit(f"{path} exists already")
    ps, upcoming, base = gitparts.parts(repo, week, practical)
    scope = f"{'w' + str(week) if isinstance(week, int) else week.lower()}p1"
    if not ps:
        raise SystemExit(f'no commits like "feat({scope}): ..." or "Week {week} Part 1: ..." in {repo}')
    # several repos in one week get their own key (W18-aiofetch) and share the week (W18)
    open(path, "w").write(
        f'KEY, NAME, WEEK = "{key}", "{name or os.path.basename(repo.rstrip("/"))}", "{gitparts.week_label(week)}"\n'
        f'# The Parts come from git ("feat({scope}): ..." commits); columns, runs and summaries are worked out.\n'
        f'REPO = "{os.path.relpath(repo, WORKSPACE)}"\n'
        f'WEEK_NUM, PRACTICAL = {week!r}, {practical and os.path.relpath(practical, WORKSPACE)!r}\n')  # None or a path
    print(f"wrote {path}: Parts {', '.join(p['label'] for p in ps)}" + (f", upcoming {', '.join(u for u, _ in upcoming)}" if upcoming else ""))
    install_hooks(repo, ROOT)  # before the first build: a build that fails still leaves the hook
    build()
    data = json.load(open(f"build/proj_{key}.json"))
    last = [r for r in data["runs"] if r["part"] == ps[-1]["label"]]
    print("check once: START is your code's first call, END is what it got back")
    for r in last:
        print(f"  {r['title']}: {', '.join(r.get('expects', [])[:2])}")


def main():
    ap = argparse.ArgumentParser(description="keep the project map in step with the code")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--check", action="store_true")
    b.add_argument("--accept", action="store_true", help="checks, then saves this map as the expected one (an old week changed on purpose)")
    sub.add_parser("update")
    sub.add_parser("note")
    h = sub.add_parser("hook")
    h.add_argument("project")
    i = sub.add_parser("init")
    i.add_argument("key")
    i.add_argument("repo")
    i.add_argument("--week", required=True, help="7, or PF1 for the production bridge")
    i.add_argument("--practical")
    i.add_argument("--name")
    a = ap.parse_args()
    if a.cmd == "build":
        build(check=a.check or a.accept, accept=a.accept)
        print(f"built {PAGE}")
    elif a.cmd == "update":
        update()
    elif a.cmd == "note":
        note()
    elif a.cmd == "hook":
        hook(a.project)
    else:
        week = int(a.week) if a.week.isdigit() else a.week.upper()
        init(a.key, os.path.abspath(a.repo), week, a.practical and os.path.abspath(a.practical), a.name)


if __name__ == "__main__":
    main()
