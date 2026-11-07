"""Every public function of every Part of every week, typed into "a function of yours" with nothing given: which way
the playground sets it up (as typed, 1 a test, 2 your code that calls it, 3 built, 4 asks you), and whether the run
really starts at that function. Measured, in a throwaway folder (your runs/ are never touched).

usage: python3 flowmap_playground/tests/proof_setup.py [W4 ...]      prints one line per function and a table
"""

import collections
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src", "flowmap_playground"))
import server  # noqa: E402
import flowmap  # noqa: E402


def main(weeks):
    home = tempfile.mkdtemp(prefix="flowmap-proof-")
    os.symlink(os.path.join(os.path.dirname(HERE), "drivers"), os.path.join(home, "drivers"))
    server.HERE = home
    table, slow = collections.Counter(), []
    try:
        for key, p in server.projects(weeks or None).items():
            for part in flowmap.part_list(p["c"]):
                if not server.row(p, part["label"]):
                    continue
                ix = server.index_of(server.code_copy(p["c"], part["commit"]))
                fns = sorted(fn for fn in ix.defs if "<" not in fn and not any(x.startswith("_") for x in fn.split(".")[1:])
                             and ix.kind(fn) in ("function", "method", "classmethod", "staticmethod", "class")
                             and not ix.interface(ix.owner(fn) or fn))  # an interface's methods have no body to run
                for fn in fns:
                    t = time.perf_counter()
                    try:
                        d = server.play(p, part["label"], "call", f"{fn}()")
                        starts = [e["fn"] for e in d["events"] if e["k"] in ("call", "new") and not e["fn"].startswith("test_playground.")]
                        target = fn
                        how = (d["setup"] or {}).get("how", "as typed")
                        result = "starts at it" if starts and starts[0] == target else f"starts at {starts[0] if starts else 'nothing'}"
                        if d["status"] not in ("passed",) and not d.get("returned"):
                            result += f" · {d['status'][:70]}"
                    except server.NeedsSetup as exc:
                        how, result = "asks", ", ".join(a["name"] for a in exc.ask)
                    except server.TooLong as exc:  # Enter with Shrink's suggestions, as you would (again if still too long)
                        how, result, sent = "too long", f"nothing to shrink: {exc.note or exc}"[:90], []
                        for _ in range(3):
                            if not exc.shrink:
                                break
                            sent = server.merged(sent, [{"fn": k["fn"], "name": k["name"], "value": k["suggest"]} for k in exc.shrink])
                            said = ", ".join(f"{k['fn']}·{k['name']}={k['value']}" for k in sent)
                            try:
                                d = server.play(p, part["label"], "call", f"{fn}()", changes=sent)
                                result = f"with Shrink's {said}: {len(d['events'])} events"
                                break
                            except server.TooLong as again:
                                exc, result = again, f"still too long with {said}"
                    except ValueError as exc:  # a class with no code of its own, or a name Python hides: said plainly
                        how = "no code" if "runs none of your code" in str(exc) or "hides it" in str(exc) else "error"
                        result = str(exc)[:90]
                    took = time.perf_counter() - t
                    table[(key, how)] += 1
                    slow.append(took)
                    print(f"{key} Part {part['label']:>2} {fn:<48} {how:<9} {took:5.1f} s  {result}", flush=True)
    finally:
        shutil.rmtree(home, ignore_errors=True)
    hows = ["as typed", "test", "caller", "built", "asks", "too long", "no code", "error"]
    print("\nweek  " + "  ".join(f"{h:>8}" for h in hows))
    for key in sorted({k for k, _ in table}):
        print(f"{key:<5} " + "  ".join(f"{table[(key, h)]:>8}" for h in hows))
    print(f"{len(slow)} runs, {sum(slow):.0f} s in all, the slowest {max(slow):.1f} s")


if __name__ == "__main__":
    main(sys.argv[1:])
