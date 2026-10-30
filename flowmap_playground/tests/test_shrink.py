"""Shrink and Clear. A run too long to step through says which values in your code made it long, each with a suggestion
(the value your tests use, else a small one); you run with them, change them, or type one into the call
(lab.main(requests=5) goes down to load). A change is kept for that week until you press Clear. Your code and the map's
copies of it are never changed: only the run's own copy, in memory.

Everything runs in a throwaway folder (never your runs/). run: python3 -m unittest flowmap_playground/tests/test_shrink.py
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PLAYGROUND = os.path.dirname(HERE)
sys.path.insert(0, PLAYGROUND)
import server  # noqa: E402
import pickruns  # noqa: E402

BROWSER = bool(shutil.which("google-chrome") and shutil.which("node"))
SKIP = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}


def fingerprints(found):
    """Every file of each week's project and of the map's code copies: {path: md5}."""
    out = {}
    roots = [p["c"]["REPO"] for p in found.values()] + [os.path.join(server.TESTS_MAP, "exports")]
    for root in roots:
        for d, subs, files in os.walk(root):
            subs[:] = [s for s in subs if s not in SKIP]
            for f in files:
                path = os.path.join(d, f)
                out[path] = hashlib.md5(open(path, "rb").read()).hexdigest()
    return out


def untouched(test, before, found):
    """No file that was there before changed or went (new code copies may appear)."""
    now = fingerprints(found)
    test.assertEqual({p: h for p, h in before.items() if now.get(p) != h}, {})


LOAD20 = [{"fn": "lab.load", "name": "requests", "value": 20}]


def loads(run):
    return [dict((k, v.get("v")) for k, v in e["args"]) for e in run["events"] if e["k"] == "call" and e["fn"] == "lab.load"]


class Shrink(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="flowmap-shrink-")
        os.symlink(os.path.join(PLAYGROUND, "drivers"), os.path.join(cls.home, "drivers"))
        server.HERE = cls.home
        cls.found = server.projects(only=("W2", "W5"))
        cls.w5, cls.w2 = cls.found["W5"], cls.found["W2"]
        cls.before = fingerprints(cls.found)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)

    def test_lab_main_too_long_names_the_value_that_made_it_long(self):
        with self.assertRaises(server.TooLong) as caught:
            server.play(self.w5, "1", "call", "lab.main()")
        knobs = {(k["fn"], k["name"]): k for k in caught.exception.shrink}
        k = knobs[("lab.load", "requests")]
        self.assertEqual((k["code"], k["suggest"], k["long"]), ("200", 20, True))
        self.assertEqual(k["why"], "your test uses 20")
        self.assertLess(k["steps"], pickruns.MAX_EVENTS)  # the estimate for the suggestion
        self.assertIn("too long to step through", str(caught.exception))

    def test_with_the_suggestion_lab_main_runs_and_load_gets_it(self):
        run = server.play(self.w5, "1", "call", "lab.main()", changes=LOAD20)
        self.assertLessEqual(len(run["events"]), pickruns.MAX_EVENTS)
        self.assertEqual([x["requests"] for x in loads(run)], [20, 20])
        self.assertEqual(run["changes"], [{"fn": "lab.load", "name": "requests", "code": "200", "value": 20}])

    def test_your_own_value_instead_of_the_suggestion(self):
        run = server.play(self.w5, "1", "call", "lab.main()", changes=[{"fn": "lab.load", "name": "requests", "value": 3}])
        self.assertEqual([x["requests"] for x in loads(run)], [3, 3])

    def test_typing_the_value_into_the_call_sends_it_down_to_load(self):
        run = server.play(self.w5, "1", "call", "lab.main(requests=5)")
        self.assertEqual([x["requests"] for x in loads(run)], [5, 5])
        self.assertEqual(run["changes"], [{"fn": "lab.load", "name": "requests", "code": "200", "value": 5}])

    def test_a_name_nothing_below_takes_says_so(self):
        with self.assertRaises(ValueError) as caught:
            server.play(self.w5, "1", "call", "lab.main(nonsense=5)")
        self.assertIn("nonsense", str(caught.exception))

    def test_a_change_is_kept_for_the_week_until_clear(self):
        server.clear("W5")
        server.record("W5", self.w5, "1", "call", "lab.main()", changes=LOAD20)
        self.assertEqual(server.week_changes("W5"), LOAD20)
        run, _ = server.record("W5", self.w5, "1", "call", "lab.main()")  # sent with no changes: the kept one is used
        self.assertEqual([x["requests"] for x in loads(run)], [20, 20])
        server.clear("W5")
        self.assertEqual(server.week_changes("W5"), [])
        with self.assertRaises(server.TooLong):
            server.record("W5", self.w5, "1", "call", "lab.main()")

    def test_a_kept_change_this_code_doesnt_have_is_named_and_not_used(self):
        gone = {"fn": "lab.gone", "name": "n", "value": 3}  # a function a later commit renamed, or another Part's
        run = server.play(self.w5, "1", "call", "lab.main()", changes=LOAD20 + [gone])
        self.assertEqual([x["requests"] for x in loads(run)], [20, 20])
        self.assertEqual(run["missing"], ["lab.gone · n"])
        self.assertIn("lab.gone · n", run["note"])

    def test_kept_changes_are_on_the_page_after_a_restart(self):
        server.clear("W5")
        server.record("W5", self.w5, "1", "call", "lab.main()", changes=LOAD20)
        srv = server.serve(0, only=("W5",), suggest=False)  # a new server: it knows only what is on disk
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            page = urllib.request.urlopen(f"http://127.0.0.1:{srv.server_port}/", timeout=60).read().decode()
        finally:
            srv.shutdown()
            srv.server_close()
            server.clear("W5")
        data = json.loads(page.split("window.PLAYGROUND = ", 1)[1].split(";\n", 1)[0])
        self.assertEqual(data["changes"]["W5"], LOAD20)

    def test_a_saved_run_plays_again_with_its_changes_after_a_commit(self):
        server.clear("W5")
        server.record("W5", self.w5, "1", "call", "lab.main()", changes=LOAD20)
        server.clear("W5")  # the week's changes are gone; the run keeps the ones it was made with
        runs = server.saved_runs("W5")
        now = runs[-1]["export"]
        runs[-1]["export"] = "exports/0000000"  # as if it had been recorded on the commit before
        server.save_runs("W5", runs)
        server.follow("W5", self.w5, log=lambda *a: None)
        saved = server.saved_runs("W5")[-1]
        self.assertEqual(saved["export"], now)
        run = json.load(open(os.path.join(self.home, "runs", "W5", saved["file"])))
        self.assertEqual([x["requests"] for x in loads(run)], [20, 20])

    def test_a_function_reached_through_your_code_traces_back_through_it(self):
        # cli.run() is set up by running cli.main (setup step 2): its jobs come from build_parser's --jobs default
        with self.assertRaises(server.TooLong) as caught:
            server.play(self.w2, "5", "call", "cli.run()")
        knobs = {(k["fn"], k["name"]): k for k in caught.exception.shrink}
        self.assertIn(("cli.build_parser", "--jobs"), knobs)
        k = knobs[("cli.build_parser", "--jobs")]
        run = server.play(self.w2, "5", "call", "cli.run()", changes=[{"fn": k["fn"], "name": k["name"], "value": k["suggest"]}])
        self.assertLessEqual(len(run["events"]), pickruns.MAX_EVENTS)

    def test_a_size_that_comes_from_your_input_is_named_not_changed(self):
        with self.assertRaises(server.TooLong) as caught:
            server.play(self.w2, "5", "cli", "--jobs 300")
        self.assertIn("--jobs", caught.exception.note)
        self.assertNotIn("jobs", [k["name"] for k in caught.exception.shrink])

    def test_z_your_code_and_its_copies_are_untouched(self):
        untouched(self, self.before, self.found)


@unittest.skipUnless(BROWSER, "needs Chrome and node")
class ShrinkInPage(unittest.TestCase):
    """The real page: a run too long to step through, the Shrink row, a run with its suggestion, Clear."""

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="flowmap-shrinkpage-")
        os.symlink(os.path.join(PLAYGROUND, "drivers"), os.path.join(cls.home, "drivers"))
        server.HERE = cls.home
        cls.srv = server.serve(0, only=("W5",), suggest=False)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.home, ignore_errors=True)

    def test_too_long_then_the_suggestion_then_clear(self):
        r = subprocess.run(["node", os.path.join(HERE, "shrink_in_page.mjs"), f"http://127.0.0.1:{self.srv.server_port}/", "W5", "lab.main()"],
                           capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-800:])
        too_long, ran, cleared = json.loads(r.stdout)["steps"]
        self.assertIn("too long to step through", too_long["said"])
        self.assertEqual([{k: x[k] for k in ("name", "code", "value")} for x in too_long["rows"]],
                         [{"name": "lab.load · requests", "code": "200 →", "value": "20"}])
        self.assertIn("long", too_long["rows"][0]["cls"])
        self.assertTrue(too_long["rows"][0]["why"].startswith("your test uses 20 · ≈ "))
        self.assertTrue(ran["run"].startswith("lab.main() · "), ran["run"])
        self.assertEqual([(x["name"], x["value"], "mine" in x["cls"]) for x in ran["rows"]], [("lab.load · requests", "20", True)])
        self.assertEqual(ran["mine"], ["lab.load"])
        self.assertEqual(ran["box"], "requests = 20 · yours (the code says 200)")
        self.assertEqual((cleared["rows"], cleared["said"], cleared["clear"]), ([], "your code's own values again", False))
        self.assertEqual(server.week_changes("W5"), [])


if __name__ == "__main__":
    unittest.main()
