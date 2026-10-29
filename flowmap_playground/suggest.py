"""A Part's Try: suggestions, from what that Part's tests passed into your code (harvest.py notes it).

1. Each entry of the Part names the functions it feeds and a rule turning a test's values into the words you'd type
   (drivers/w4.py: get_item <- client.AiofetchClient.get_item(1500) gives "1500").
2. A function the Part added, whose tests gave it only plain values, gets "call": record.parse_line("…").
3. The tests the Part added come first. The server plays each one on the Part's code; one that doesn't run is dropped.
4. Up to 4 are kept: one that ends fine, one that raises (or exits non-zero), then different endings.
   Each says which test it came from and how it ended: "Get item returns the shape the server sent: ↩ ItemMissing".
"""

import math
import re

import pickruns  # flowmap_tests/tools: a test's name as a title

TRIES = 10  # played per Part, at most
PER_ENTRY = 3  # tried per entry, at most (per function for "call")
SCENERY_ARGS = {"port", "host"}  # where a test's own server listened: gone by the time you'd type it
FAKE_NAME = re.compile(r"(Mock|Fake|Stub|Dummy)[A-Z]")


def literal(v):
    """Text, numbers, True/False/None, and lists or dicts of them: what a typed call can hold."""
    if v is None or isinstance(v, (bool, int, str)):
        return True
    if isinstance(v, float):
        return math.isfinite(v)
    if isinstance(v, list):
        return all(literal(x) for x in v)
    if isinstance(v, dict):
        return not any(k.startswith("@") for k in v) and all(literal(x) for x in v.values())
    return False


def fake_modules(calls, fakes):
    """The modules of the test fakes (FlakyAPI, MockServer): their functions are the tests' scenery, not yours to try."""
    names = set(fakes) | {c["fn"].rsplit(".", 1)[0] for c in calls if any(FAKE_NAME.match(p) for p in c["fn"].split("."))}
    return {n.split(".")[0] for n in names}


def as_call(call, scenery):
    """client.AiofetchClient(...) / storage.is_json_object({...}) for a call with plain values, or None."""
    fn = call["fn"]
    parts = fn.split(".")
    if parts[0] in scenery or any(p.startswith("_") and p != "__init__" for p in parts[1:]) or call.get("varargs"):
        return None
    if call.get("bound") == "self" and parts[-1] != "__init__":
        return None  # a method needs its object, which a typed call can't build
    if not all(literal(v) for v in call["args"].values()) or SCENERY_ARGS & set(call["args"]):
        return None
    target = fn[: -len(".__init__")] if parts[-1] == "__init__" else fn
    args = list(call["args"].items())
    pos, kw = args[: call.get("positional", len(args))], args[call.get("positional", len(args)):]
    text = f"{target}(" + ", ".join([repr(v) for _, v in pos] + [f"{k}={v!r}" for k, v in kw]) + ")"
    return text if len(text) <= 300 else None


def candidates(block, now, before, fakes=(), private=()):
    """[(entry, text, test)] to play for a Part, best first. `now`/`before`: the harvests of this Part and the one
    before it. `private`: words that must never be suggested (this machine's folders)."""
    old_tests = {c["test"] for c in before}
    old_fns = {c["fn"] for c in before}
    entries = list(block["entries"].items())
    covered = {fn for _, e in entries for fn in e.get("from", {})}
    scenery = fake_modules(now, fakes)
    by_test = {}
    for c in now:
        by_test.setdefault(c["test"], []).append(c)
    best = {}
    for test, calls in by_test.items():
        new = test not in old_tests
        for i, call in enumerate(calls):
            found = []
            for rank, (name, e) in enumerate(entries):
                rule = e.get("from", {}).get(call["fn"])
                if rule:
                    try:
                        found.append((rank, name, rule(call["args"], calls[:i])))
                    except Exception:  # a value of a shape the rule didn't expect: no suggestion from it
                        pass
            if "call" in block["entries"] and call["fn"] not in covered and call["fn"] not in old_fns:
                found.append((len(entries), "call", as_call(call, scenery)))
            for rank, name, text in found:
                if isinstance(text, str) and text.strip() and len(text) <= 300 and not any(p in text for p in private):
                    key = (not new, rank, len(text))
                    if (name, text) not in best or key < best[(name, text)][0]:
                        best[(name, text)] = (key, test)
    out, per = [], {}
    for (name, text), (key, test) in sorted(best.items(), key=lambda kv: (kv[1][0], kv[0])):
        if per.get(what(name, text), 0) < (PER_ENTRY if name != "call" else 1) and len(out) < TRIES:
            per[what(name, text)] = per.get(what(name, text), 0) + 1
            out.append((name, text, test))
    return out


def what(entry, text):
    """What a suggestion runs: its entry, or for "call" the function it calls."""
    return entry if entry != "call" else "call " + text.split("(")[0]


def ending(run, entry=None):
    """How a played run ended, in a few words: "raises ItemMissing", "exit 1", "↩ ItemFound", "↩ {rows, stats}"."""
    if run["status"].startswith("raised "):
        return "raises " + run["status"][len("raised "):].split(":")[0]
    if run.get("exit") is not None:  # a whole number back: a command's exit code, or what a function you called gave
        return f"exit {run['exit']}" if entry != "call" else f"↩ {run['exit']}"
    if run.get("returned"):
        return "↩ {" + ", ".join(k for k, _ in run["returned"].get("items", [])) + "}"
    you = next((e["id"] for e in run["events"] if e["k"] == "call" and e["fn"].startswith("test_playground.")), None)
    mine = {e["id"] for e in run["events"] if e["k"] in ("call", "new") and e.get("parent") == you}
    gave = [e["value"].get("t") for e in run["events"] if e["k"] == "return" and e.get("id") in mine
            and e.get("value", {}).get("t") not in (None, "None") and not e["fn"].rsplit(".", 1)[-1].startswith("_")]
    made = [e["fn"].rsplit(".", 1)[-1] for e in run["events"] if e["k"] == "new" and e.get("id") in mine]
    return "↩ " + gave[-1] if gave else "↩ " + made[-1] if made else "ok"


def choose(tried, most=4):
    """From [((entry, text, test), its run or None)], best first: up to `most` suggestions for the page."""
    played = []
    for (entry, text, test), run in tried:
        if run:
            end = ending(run, entry)
            bad = end.startswith("raises") or (end.startswith("exit") and end != "exit 0")
            title = pickruns.title(test.split("::")[-1].split("[")[0])
            played.append({"entry": entry, "input": text, "kind": "bad" if bad else "good", "about": f"{title}: {end}", "end": end})
    picked = []
    for kind in ("good", "bad"):  # one that ends fine, one that doesn't
        s = next((s for s in played if s["kind"] == kind), None)
        if s:
            picked.append(s)
    for s in played:  # then different endings (or entries, or functions) first
        if len(picked) < most and s not in picked and (what(s["entry"], s["input"]), s["end"]) not in {(what(p["entry"], p["input"]), p["end"]) for p in picked}:
            picked.append(s)
    picked += [s for s in played if s not in picked][: most - len(picked)]
    for i, s in enumerate(picked):
        if i >= 2 or (i == 1 and s["kind"] == picked[0]["kind"]):
            s["kind"] = "more"
    return [{k: s[k] for k in ("entry", "input", "kind", "about")} for s in picked]
