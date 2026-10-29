"""Every suggested input of every Part, recorded on that Part's own code: each one runs, a good one doesn't raise, and
together they reach every component (map column) that Part has. Fails naming the Part and what it never reached.

A component nothing can reach yet (starter code a later Part starts using) is left out only when the Part's row says
why, under "not yet". The note must stay true: the test fails if that component isn't in the Part, or is reached.

run: python3 -m unittest discover -s flowmap_playground/tests -p "test_scenarios.py"   (a few minutes)
"""

import concurrent.futures
import importlib
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLAYGROUND = os.path.dirname(HERE)
DRIVERS = os.path.join(PLAYGROUND, "drivers")
TESTS_MAP = os.path.join(os.path.dirname(PLAYGROUND), "flowmap_tests")
sys.path[:0] = [DRIVERS, os.path.join(TESTS_MAP, "tools")]
import flowmap  # noqa: E402
import pickruns  # noqa: E402

OUT = tempfile.mkdtemp(prefix="flowmap-scenarios-")


def weeks():
    """(key, its settings, its driver module) for every week that has a driver."""
    os.chdir(TESTS_MAP)
    for cfg, c in flowmap.projects():
        path = os.path.join(DRIVERS, c["KEY"].lower() + ".py")
        if os.path.exists(path):
            yield c["KEY"], c, importlib.import_module(c["KEY"].lower())


def record(c, driver, part, commit, scenario):
    import subprocess
    entry, text, kind, about = scenario
    os.chdir(TESTS_MAP)
    export = os.path.abspath(flowmap.export(c["REPO"], commit))
    out = os.path.join(OUT, f"{c['KEY']}_{part}_{abs(hash(scenario))}.json")
    python = c.get("PYTHON") or os.path.join(c["REPO"], ".venv", "bin", "python")
    path = os.path.join(DRIVERS, c["KEY"].lower() + ".py")  # the real file (another test may have imported it elsewhere)
    subprocess.run([python, os.path.join(TESTS_MAP, "tools", "trace.py"), export, f"play:{path}:{part}:{entry}", out, text],
                   capture_output=True, text=True, timeout=120, env=pickruns.safe_env())
    return json.load(open(out)) if os.path.exists(out) else None


class EveryPart(unittest.TestCase):
    def test_every_scenario_runs_and_together_they_reach_every_component(self):
        jobs = []
        for key, c, driver in weeks():
            data = json.load(open(os.path.join(TESTS_MAP, "build", f"proj_{key}.json")))
            column = {card: col["name"].strip() for col in data["map"]["columns"] if col["name"] not in ("START", "END") for card in col["cards"]}
            commits = {p["label"]: p["commit"] for p in flowmap.part_list(c)}
            for part, block in driver.PARTS.items():
                with self.subTest(week=key, part=part):
                    self.assertIn(part, commits, f"{key}: the driver has a Part {part} the map doesn't")
                    kinds = [s[2] for s in block["scenarios"]]
                    self.assertTrue("good" in kinds and "bad" in kinds and len(kinds) <= 4, f"{key} Part {part}: a good one, a bad one, at most 4")
                    for s in block["scenarios"]:
                        self.assertIn(s[0], block["entries"], f"{key} Part {part}: {s[1]!r} uses an entry the Part doesn't have")
                nodes = next(p["nodes"] for p in data["parts"] if p["label"] == part)
                present = {column[n] for n in nodes if n in column}
                jobs.append((key, c, driver, part, commits[part], block, column, present))
        alias = {}
        for key, c, _ in weeks():
            alias[key] = c.get("ALIASES", {})
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            done = {(j[0], j[3], s): pool.submit(record, j[1], j[2], j[3], j[4], s) for j in jobs for s in j[5]["scenarios"]}
        for key, c, driver, part, commit, block, column, present in jobs:
            reached = set()
            for s in block["scenarios"]:
                d = done[(key, part, s)].result()
                with self.subTest(week=key, part=part, scenario=s[1]):
                    self.assertIsNotNone(d, f"{key} Part {part} {s[1]!r}: the recorder made no run")
                    yours = [e for e in d["events"] if e["k"] in ("call", "new") and not e["fn"].startswith("test_playground.")]
                    self.assertTrue(yours, f"{key} Part {part} {s[1]!r}: none of your code ran ({d['status']})")
                    self.assertLessEqual(len(d["events"]), pickruns.MAX_EVENTS, f"{key} Part {part} {s[1]!r}: too long to step through")
                    if s[2] == "good":
                        self.assertEqual(d["status"], "passed", f"{key} Part {part} {s[1]!r}: a good scenario raised")
                fns = [e["fn"] for e in d["events"] if e["k"] in ("call", "new")] + [o["cls"] for o in d["objects"].values()]
                for fn in fns:
                    fn = alias[key].get(fn.removesuffix(".__init__"), fn.removesuffix(".__init__"))
                    if fn in column:
                        reached.add(column[fn])
            not_yet = block.get("not yet", {})
            with self.subTest(week=key, part=part, coverage=True):
                self.assertEqual(sorted(present - reached - set(not_yet)), [], f"{key} Part {part}: these components are never reached")
                self.assertEqual(sorted(set(not_yet) - present), [], f"{key} Part {part}: 'not yet' names components this Part doesn't have")
                self.assertEqual(sorted(set(not_yet) & reached), [], f"{key} Part {part}: 'not yet' components are reached now: remove the note")
                self.assertTrue(all(why.strip() for why in not_yet.values()), f"{key} Part {part}: every 'not yet' needs its reason")


class EveryPartsTests(unittest.TestCase):
    def test_every_part_gets_suggestions_from_its_own_tests(self):
        """The Try: lists the page shows (made from each Part's tests, see suggest.py): every Part gets at least one,
        each one played on that Part's code. A Part whose tests give nothing usable says why under "no suggestions" in
        its row (then the driver's own are shown); the note must stay true."""
        import shutil
        import server
        home = tempfile.mkdtemp(prefix="flowmap-suggest-")
        os.symlink(DRIVERS, os.path.join(home, "drivers"))
        server.HERE = home
        try:
            for key, p in server.projects().items():
                made = server.suggestions(key, p, log=lambda m: None)
                for part, block in server.driver_module(p["driver"]).PARTS.items():
                    with self.subTest(week=key, part=part):
                        note = block.get("no suggestions")
                        if note:
                            self.assertTrue(note.strip(), f"{key} Part {part}: a 'no suggestions' note needs its reason")
                            self.assertEqual(made.get(part), [], f"{key} Part {part}: its tests give suggestions now: remove the note")
                            continue
                        self.assertTrue(made.get(part), f"{key} Part {part}: none of its tests gave a suggestion that plays. Give an entry "
                                                        f"a rule under 'from' (drivers/{key.lower()}.py), or the Part a 'no suggestions' note")
                        for s in made[part]:
                            self.assertIn(s["entry"], block["entries"])
                            self.assertIn(s["kind"], ("good", "bad", "more"))
                            self.assertTrue(s["about"] and s["input"].strip())
        finally:
            shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
