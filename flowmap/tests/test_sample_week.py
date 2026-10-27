"""The whole pipeline on a sample repo: a Week 4 Part and two Week 5 Parts, built by the real flowmap.py build --check
in a sandbox folder (its own cfg/, runs/, exports/, build/; the tools, page and checks are this flowmap's)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from test_parts import Repo  # noqa: E402
from test_recorder import PY, pickruns  # noqa: E402

BETA = '''from demo import core


def double_all(xs):
    return core.apply(lambda_free_double, xs)


def lambda_free_double(x):
    return x * 2
'''
TEST_BETA = '''from demo import core
from demo.adapters import beta


def plus_two(x):  # handed in: from Week 5 it shows, in the "from the test" column
    return x + 2


def test_beta_hands_in_a_function():
    assert core.apply(plus_two, beta.double_all([1, 2])) == [4, 6]
'''
TEST_LATER = '''from demo import core


def test_later_is_built():
    assert core.later() == [core.make("a"), core.make("bb")]
'''


@unittest.skipUnless(PY and shutil.which("google-chrome") and shutil.which("node"), "needs a project Python, Chrome and node")
class SampleWeek(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repo = cls.repo = Repo()
        shutil.copytree(os.path.join(HERE, "sample"), repo.dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
        first = repo.commit("feat(w4p1): the sample project")
        box = cls.box = tempfile.mkdtemp(prefix="flowmap-box-")
        os.makedirs(os.path.join(box, "runs"))
        # one run set by hand (like cfg/w3.py's RUN_META), recorded on Part 1's code
        subprocess.run([PY, os.path.join(ROOT, "tools", "trace.py"), repo.dir, "tests/unit/test_core.py::test_assert_lines",
                        os.path.join(box, "runs", "asserts.json")], capture_output=True, timeout=90, env=pickruns.safe_env())
        hand = [("asserts.json", {"key": "asserts", "part": "1", "export": f"exports/{first}", "title": "Assert lines",
                                  "test": "tests/unit/test_core.py", "fn": "test_assert_lines"})]
        open(os.path.join(repo.dir, "src/demo/adapters/beta.py"), "w").write(BETA)
        open(os.path.join(repo.dir, "tests/unit/test_beta.py"), "w").write(TEST_BETA)
        repo.commit("feat(w5p1): a second adapter")
        core = os.path.join(repo.dir, "src/demo/core.py")
        src = open(core).read().replace('raise NotImplementedError("Stage 1")  # a stub without a TODO: not built yet',
                                        'return [make("a"), make("bb")]')
        open(core, "w").write(src)
        open(os.path.join(repo.dir, "tests/unit/test_later.py"), "w").write(TEST_LATER)
        repo.commit("feat(w5p2): later is built")
        for d in ("tools", "page", "checks"):
            os.symlink(os.path.join(ROOT, d), os.path.join(box, d))
        os.makedirs(os.path.join(box, "cfg"))
        for key, week in (("W4S", 4), ("W5S", 5)):
            open(os.path.join(box, "cfg", f"{key.lower()}.py"), "w").write(
                f'KEY, NAME, WEEK = "{key}", "sample", "W{week}"\nREPO = {repo.dir!r}\nWEEK_NUM, PRACTICAL = {week}, None\nPYTHON = {PY!r}\n'
                + (f"RUN_META = {hand!r}\n" if week == 4 else ""))
        cls.result = subprocess.run([sys.executable, os.path.join(box, "tools", "flowmap.py"), "build", "--check"],
                                    capture_output=True, text=True, timeout=900)
        cls.check = open(os.path.join(box, "build", "check.txt")).read()
        cls.data = {k: json.load(open(os.path.join(box, "build", f"proj_{k}.json"))) for k in ("W4S", "W5S")}
        cls.summary = json.load(open(os.path.join(box, "build", "summary.json")))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.box, ignore_errors=True)
        shutil.rmtree(cls.repo.dir, ignore_errors=True)

    def part(self, key, label):
        return next(p for p in self.data[key]["parts"] if p["label"] == label)

    def test_the_build_and_every_guard_pass(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr[-2000:])
        self.assertEqual(self.check.splitlines()[0], "ok", self.check)

    def test_parts_from_conventional_commits(self):
        self.assertEqual([p["label"] for p in self.data["W4S"]["parts"]], ["1"])
        self.assertEqual([p["label"] for p in self.data["W5S"]["parts"]], ["W4", "1", "2"])

    def test_a_stub_joins_the_map_when_it_is_built_and_an_abstract_method_stays(self):
        self.assertNotIn("core.later", self.part("W5S", "1")["nodes"])
        self.assertIn("core.later", self.part("W5S", "2")["nodes"])
        self.assertIn("core.Store.get", self.part("W4S", "1")["nodes"])

    def test_fakes_by_name(self):
        self.assertIn("core.FakeStore", self.data["W4S"]["map"]["wiring"])

    def test_a_subpackage_is_one_column(self):
        cols = {c["name"]: c for c in self.data["W5S"]["map"]["columns"]}
        self.assertEqual(cols["adapters"]["file"], "adapters/")
        self.assertIn("adapters.beta.double_all", cols["adapters"]["cards"])

    def test_every_part_has_runs_from_tests_in_subfolders(self):
        for key in ("W4S", "W5S"):
            parts = {r["part"] for r in self.data[key]["runs"]}
            self.assertTrue({p["label"] for p in self.data[key]["parts"] if not p.get("base") and p["label"] != "W4"} <= parts, key)
            self.assertTrue(all(r["test"].startswith("tests/unit/") for r in self.data[key]["runs"]))

    def test_every_run_starts_with_your_call_and_ends_with_an_output(self):
        for key, parts in self.summary.items():
            for label, p in parts.items():
                for r in p["runs"]:
                    self.assertTrue(r["start"] and r["end"], (key, label, r))

    def test_on_assert_lines_only_the_checks_are_hidden(self):
        run = next(r for r in self.summary["W4S"]["1"]["runs"] if r["title"] == "Assert lines")
        self.assertIn("core.make", run["calls"])  # assert core.make("abc").size == 3: the call being tested
        self.assertNotIn("core.Item.ok", run["calls"])  # assert item.ok: a yes/no read
        self.assertEqual(run["start"], "make('abc')")

    def test_test_code_in_the_middle_shows_from_week_5_only(self):
        run = next(r for r in self.summary["W5S"]["1"]["runs"])
        self.assertIn("test_beta.plus_two", run["calls"])
        w5 = self.data["W5S"]
        cols = {c["name"]: c for c in w5["map"]["columns"]}
        self.assertIn("test_beta.plus_two", cols["from the test"]["cards"])
        self.assertTrue(w5["nodes"]["test_beta.plus_two"]["mid"])
        self.assertIn("test_beta.plus_two", self.part("W5S", "1")["nodes"])
        w4 = self.data["W4S"]
        self.assertNotIn("from the test", [c["name"] for c in w4["map"]["columns"]])
        self.assertFalse(any(n.get("mid") for n in w4["nodes"].values()))


if __name__ == "__main__":
    unittest.main()
