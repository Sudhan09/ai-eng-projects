"""The browser check after a commit looks again only at the weeks whose map changed (src/flowmap_tests/flowmap.py, page_check).
A week that didn't change keeps its last clean result; a change to the page or the check itself checks every week."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_recorder import ROOT, flowmap  # noqa: E402


def smoke(keys, bad=()):
    """What checks/smoke.js writes for these weeks: a Part line and a run line each (and a problem for each week in
    `bad`), then the page's own line."""
    lines = ["SMOKE OK"] + [f'PROBLEM {k} Part 1 "A run of {k}": END shows no output' for k in keys if k in bad]
    for k in keys:
        lines += [f"{k} Part 1: columns [START, END]; 3 cards (3 new, 0 changed), 2 lines; overlaps 0; through cards 0",
                  f'   ▶ A run of {k}: starts at 1/9 "f()", ends "↩ 1"; box now "END"']
    lines.append(f"speed menu: 1×; panel: Who's waiting; views: 0 switches; parts {keys[0]}: 1")
    summary = {k: {"1": {"commit": "abc", "cards": 3, "lines": 2, "runs": []}} for k in keys}
    return f'<pre id="smoke">{chr(10).join(lines)}</pre><pre id="summary">{json.dumps(summary)}</pre>'


class PageCheck(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="flowmap-pagecheck-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        for f in flowmap.CHECK_CODE:
            os.makedirs(os.path.join(self.dir, os.path.dirname(f)), exist_ok=True)
            shutil.copy(os.path.join(ROOT, f), os.path.join(self.dir, f))
        os.makedirs(os.path.join(self.dir, "build"))
        self.outs = []
        for k in ("W1", "W2"):
            out = f"build/proj_{k}.json"
            json.dump({"key": k, "parts": []}, open(os.path.join(self.dir, out), "w"))
            self.outs.append(out)
        self.cwd = os.getcwd()
        os.chdir(self.dir)
        self.addCleanup(os.chdir, self.cwd)
        self.combined, self.browsers, self.bad = [], 0, set()
        real_run, real_sp = flowmap.run, subprocess.run

        def run(*cmd, quiet=False):  # combine.py: note which weeks the check page holds
            if cmd[1] == "src/flowmap_tests/combine.py":
                self.combined.append(sorted(json.load(open(o))["key"] for o in cmd[3:]))
            return ""

        def sp(cmd, *a, **k):  # the browser: answers as smoke.js would for the weeks combined last
            if any("google-chrome" in str(x) for x in cmd):
                self.browsers += 1
                return subprocess.CompletedProcess(cmd, 0, smoke(self.combined[-1], self.bad), "")
            return real_sp(cmd, *a, **k)
        flowmap.run, subprocess.run = run, sp
        self.addCleanup(setattr, flowmap, "run", real_run)
        self.addCleanup(setattr, subprocess, "run", real_sp)

    def test_the_first_check_looks_at_every_week(self):
        text, summary = flowmap.page_check(self.outs)
        self.assertEqual(self.combined, [["W1", "W2"]])
        self.assertEqual(sorted(summary), ["W1", "W2"])
        self.assertEqual(flowmap.problems(text), [])

    def test_nothing_changed_starts_no_browser_and_keeps_every_result(self):
        first, _ = flowmap.page_check(self.outs)
        again, summary = flowmap.page_check(self.outs)
        self.assertEqual((self.browsers, again, sorted(summary)), (1, first, ["W1", "W2"]))

    def test_a_changed_week_alone_is_checked_and_the_others_keep_theirs(self):
        flowmap.page_check(self.outs)
        json.dump({"key": "W2", "parts": [1]}, open("build/proj_W2.json", "w"))  # a commit changed W2's map
        text, summary = flowmap.page_check(self.outs)
        self.assertEqual(self.combined[-1], ["W2"])
        self.assertIn("W1 Part 1: columns", text)
        self.assertIn("   ▶ A run of W1", text)
        self.assertEqual(sorted(summary), ["W1", "W2"])

    def test_a_change_to_the_page_checks_every_week_again(self):
        flowmap.page_check(self.outs)
        open("page/flowmap.html", "a").write("<!-- changed -->")
        flowmap.page_check(self.outs)
        self.assertEqual(self.combined[-1], ["W1", "W2"])

    def test_a_week_with_a_problem_is_checked_again_next_time(self):
        self.bad = {"W1"}
        text, _ = flowmap.page_check(self.outs)
        self.assertEqual(flowmap.problems(text), ['W1 Part 1 "A run of W1": END shows no output'])
        self.bad = set()  # fixed, with nothing else changed: W1 is looked at again, W2 keeps its clean result
        text, _ = flowmap.page_check(self.outs)
        self.assertEqual((self.combined[-1], flowmap.problems(text)), (["W1"], []))

    def test_lines_go_to_their_week(self):
        weeks, rest = flowmap.by_week([
            "W4 Part 2: columns", '   ▶ A run: starts', "PROBLEM W4 Part 2 \"A run\": END shows no output",
            "ERROR W5 P1 run0: boom @ x", "PROBLEM page: a local path is in the page", "speed menu: 1×"], ["W4", "W5"])
        self.assertEqual(weeks, {"W4": ["W4 Part 2: columns", "   ▶ A run: starts", 'PROBLEM W4 Part 2 "A run": END shows no output'],
                                 "W5": ["ERROR W5 P1 run0: boom @ x"]})
        self.assertEqual(rest, ["PROBLEM page: a local path is in the page", "speed menu: 1×"])


if __name__ == "__main__":
    unittest.main()
