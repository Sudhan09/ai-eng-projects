"""The playground follows your commits, as the tests map does: your saved runs move to a Part's new code, a page load
after a commit rebuilds what changed, and the Try: suggestions come from that Part's own tests.

Everything runs in a throwaway folder (never your runs/). run: python3 -m unittest flowmap_playground/tests/test_follow.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PLAYGROUND = os.path.dirname(HERE)
sys.path.insert(0, PLAYGROUND)
import server  # noqa: E402
import flowmap  # noqa: E402  (flowmap_tests/tools, put on the path by server)


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout.strip()


class Home(unittest.TestCase):
    """A playground in a throwaway folder, for W1 and W4."""

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="flowmap-follow-")
        os.symlink(os.path.join(PLAYGROUND, "drivers"), os.path.join(cls.home, "drivers"))
        server.HERE = cls.home
        cls.found = server.projects(only=("W1", "W4"))
        cls.w4 = cls.found["W4"]
        cls.parts = {p["label"]: p["commit"] for p in flowmap.part_list(cls.w4["c"])}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)

    def index(self):
        return json.load(open(os.path.join(self.home, "runs", "W4", "index.json")))

    def older(self):
        """A commit just before Part 5's, that no Part (and no run of the tests map) uses: the code a run was recorded on
        before your next commit moved the Part."""
        old = git(self.w4["c"]["REPO"], "rev-parse", "--short=7", self.parts["5"] + "~1")
        used = set(self.parts.values()) | {m["export"].split("/")[-1] for _, m in self.w4["c"].get("RUN_META", []) if "export" in m}
        if any(u.startswith(old) or old.startswith(u) for u in used):
            self.skipTest(f"{old} is a Part's commit")
        return old

    def saved_run_on(self, commit, entry="get_item", text="7"):
        """A run saved on Part 5, then pointed at `commit`, as if it had been recorded there."""
        shutil.rmtree(os.path.join(self.home, "runs"), ignore_errors=True)
        server.record("W4", self.w4, "5", entry, text)
        runs = self.index()
        runs[-1]["export"] = f"exports/{commit}"
        json.dump(runs, open(os.path.join(self.home, "runs", "W4", "index.json"), "w"))
        return runs[-1]


class SavedRuns(Home):
    def test_a_run_whose_code_copy_was_deleted_still_builds(self):
        # the tests map's update deletes copies no Part uses; your saved run still points at one (the crash of 2026-10-29)
        old = self.older()
        self.saved_run_on(old)
        shutil.rmtree(os.path.join(server.TESTS_MAP, "exports", old), ignore_errors=True)
        server.build("W4", self.w4)
        self.assertTrue(os.path.isdir(os.path.join(server.TESTS_MAP, "exports", old, "src")))
        self.assertEqual(self.index()[-1]["export"], f"exports/{old}")

    def test_a_run_whose_commit_is_gone_from_git_is_dropped_with_a_note(self):
        self.saved_run_on("0000000")
        said = []
        server.build("W4", self.w4, log=said.append)
        self.assertEqual(self.index(), [])
        self.assertFalse(os.path.exists(os.path.join(server.TESTS_MAP, "exports", "0000000")))
        self.assertTrue(any("0000000" in s for s in said), said)

    def test_after_a_new_commit_a_saved_run_is_played_again_on_the_new_code(self):
        old = self.older()
        before = self.saved_run_on(old, "get_item", "1500")
        server.follow("W4", self.w4, log=lambda m: None)
        after = self.index()[-1]
        self.assertEqual(after["export"], f"exports/{self.parts['5']}")
        self.assertEqual((after["file"], after["input"], after["part"]), (before["file"], before["input"], "5"))
        events = json.load(open(os.path.join(self.home, "runs", "W4", after["file"])))["events"]
        self.assertTrue(any(e["k"] == "call" and e["fn"].endswith(".get_item") for e in events))

    def test_a_run_that_no_longer_runs_stays_on_its_old_code(self):
        old = self.older()
        self.saved_run_on(old, "get_item", "7")
        runs = self.index()
        runs[-1]["entry"] = "gone_entry"  # as if the driver dropped the entry it was made with
        json.dump(runs, open(os.path.join(self.home, "runs", "W4", "index.json"), "w"))
        said = []
        server.follow("W4", self.w4, log=said.append)
        self.assertEqual(self.index()[-1]["export"], f"exports/{old}")
        self.assertTrue(any("stays on" in s for s in said), said)


class PageLoad(Home):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.srv = server.serve(0, only=("W1", "W4"), suggest=False)
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}/"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        super().tearDownClass()

    def get(self):
        t0 = time.time()
        page = urllib.request.urlopen(self.url, timeout=300).read().decode()
        return page, time.time() - t0

    def ask(self, body):
        req = urllib.request.Request(self.url + "play", data=json.dumps(body).encode(), method="POST",
                                     headers={"X-Flowmap-Token": self.srv.token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_a_page_load_with_no_new_commit_rebuilds_nothing(self):
        proj = os.path.join(self.home, "build", "proj_W4.json")
        was = os.path.getmtime(proj)
        page, took = self.get()
        self.assertIn(self.srv.token, page)
        self.assertEqual(os.path.getmtime(proj), was)
        self.assertLess(took, 5)

    def test_after_a_commit_a_run_asks_for_a_reload_and_the_reload_rebuilds(self):
        proj = os.path.join(self.home, "build", "proj_W4.json")
        self.srv.built["W4"] = "as it was before your last commit"
        status, got = self.ask({"key": "W4", "part": "5", "entry": "get_item", "input": "7"})
        self.assertEqual((status, got["error"]), (409, "Your code changed (a new commit) since this page loaded: reload the page"))
        was = os.path.getmtime(proj)
        page, _ = self.get()
        self.assertGreater(os.path.getmtime(proj), was)
        self.assertEqual(self.srv.built["W4"], server.signature("W4", self.w4))
        self.assertEqual(self.ask({"key": "W4", "part": "5", "entry": "get_item", "input": "7"})[0], 200)


class Suggestions(Home):
    def suggested(self, key, part):
        return server.suggestions(key, self.found[key], log=lambda m: None)[part]

    def test_w4_part3_suggestions_come_from_its_own_tests_and_each_one_plays(self):
        got = self.suggested("W4", "3")
        self.assertTrue(1 <= len(got) <= 4, got)
        tried = {(s["entry"], s["input"]) for s in got}
        self.assertIn(("get_item", "1500"), tried)  # test_get_item_returns_the_shape_the_server_sent asks for 1500
        bad = next(s for s in got if s["input"] == "1500")
        self.assertNotEqual(bad["kind"], "bad")  # get_item gives back ItemMissing; nothing raised
        self.assertIn("Get item returns the shape", bad["about"])
        self.assertTrue(all(s["kind"] in ("good", "bad", "more") and s["about"] for s in got))

    def test_a_new_function_with_plain_values_gets_a_call_suggestion(self):
        got = self.suggested("W4", "4")  # Part 4 adds storage.is_json_object, which your tests call with plain dicts
        calls = [s for s in got if s["entry"] == "call"]
        self.assertTrue(calls, got)
        self.assertTrue(all(s["input"].startswith("storage.") for s in calls), calls)

    def test_the_call_entry_runs_a_typed_call_and_never_runs_code(self):
        run = server.play(self.found["W1"], "1", "call", 'record.parse_line("2026-10-02T09:15:01Z ERROR db: connection refused")')
        self.assertEqual(run["status"], "passed")
        self.assertTrue(any(e["k"] == "call" and e["fn"] == "record.parse_line" for e in run["events"]))
        with self.assertRaisesRegex(ValueError, "plain values"):
            server.play(self.found["W1"], "1", "call", 'record.parse_line(open("/etc/passwd").read())')
        with self.assertRaisesRegex(ValueError, "no function"):
            server.play(self.found["W1"], "1", "call", 'record.nothing_here("x")')

    def test_a_new_part_without_its_own_row_borrows_the_one_before_it(self):
        # as if Part 4 had just been committed and nobody had written its row: it runs with Part 3's entries, on its
        # own code, and its suggestions come from its own tests
        w4 = {**self.w4, "parts": {k: v for k, v in self.w4["parts"].items() if k != "4"}}
        self.assertEqual(server.row(w4, "4"), "3")
        run = server.play(w4, "4", "get_item", "7")
        self.assertEqual(run["export"], f"exports/{self.parts['4']}")
        with self.assertRaisesRegex(ValueError, "jsonl isn't in Part 4"):  # Part 4's own entry needs its row
            server.play(w4, "4", "jsonl", "/items/1")
        home = server.HERE
        server.HERE = tempfile.mkdtemp(prefix="flowmap-borrow-")
        os.symlink(os.path.join(PLAYGROUND, "drivers"), os.path.join(server.HERE, "drivers"))
        try:
            made = server.suggestions("W4", w4, log=lambda m: None)
        finally:
            shutil.rmtree(server.HERE, ignore_errors=True)
            server.HERE = home
        self.assertTrue(made["4"])
        self.assertTrue({s["entry"] for s in made["4"]} <= {"get_item", "fetch_many", "call"}, made["4"])

    def test_the_page_gets_the_suggestions_and_keeps_the_drivers_as_a_fallback(self):
        made = server.suggestions("W4", self.w4, log=lambda m: None)
        parts = server.with_suggestions(self.w4["parts"], made)
        self.assertEqual(parts["3"]["scenarios"], made["3"])
        parts = server.with_suggestions(self.w4["parts"], {})
        self.assertEqual(parts["3"]["scenarios"], self.w4["parts"]["3"]["scenarios"])


if __name__ == "__main__":
    unittest.main()
