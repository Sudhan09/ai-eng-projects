"""Parts from commit messages: every format the curriculum uses finds the right Part (tools/gitparts.py)."""

import atexit
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import gitparts  # noqa: E402


class Repo:
    """A throwaway git repo: commit(msg) adds one file per commit."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="flowmap-parts-")
        atexit.register(shutil.rmtree, self.dir, True)  # gone when the tests end
        self.git("init", "-q", "-b", "main")
        self.n = 0

    def git(self, *args):
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
               "GIT_AUTHOR_DATE": f"2026-01-01T00:{self.n if hasattr(self, 'n') else 0:02d}:00", "GIT_COMMITTER_DATE": f"2026-01-01T00:{getattr(self, 'n', 0):02d}:00"}
        return subprocess.run(["git", "-C", self.dir, *args], capture_output=True, text=True, check=True, env=env).stdout.strip()

    def commit(self, msg):
        self.n += 1
        open(os.path.join(self.dir, f"f{self.n}.txt"), "w").write(msg)
        self.git("add", ".")
        self.git("commit", "-q", "-m", msg)
        return self.git("rev-parse", "--short", "HEAD")


def labels(repo, week, practical=None):
    ps, up, base = gitparts.parts(repo.dir, week, practical)
    return [(p["label"], p["title"], p["inProgress"]) for p in ps], up, base


class OldFormat(unittest.TestCase):
    def test_week_part_messages_a_lettered_part_and_a_redo(self):
        r = Repo()
        r.commit("Week 4 Part A: warm up")
        r.commit("Week 4 Part 1: strict types")
        r.commit("tidy imports")  # names no Part: joins Part 1
        r.commit("Week 4 Part 2: a seam")
        last = r.commit("Week 4 Part 2 redo: a cleaner seam")
        ps, up, base = labels(r, 4)
        self.assertEqual([p[0] for p in ps], ["1", "2"])
        self.assertEqual(gitparts.parts(r.dir, 4)[0][1]["commit"], last)  # a Part's code is its last commit
        self.assertEqual(ps[0][1], "Strict types")  # "Part A" folds into Part 1, which keeps its own title


class ConventionalCommits(unittest.TestCase):
    def test_scopes_name_the_part_and_a_squash_suffix_is_dropped(self):
        r = Repo()
        r.commit("feat(w7p1): add the stream endpoint")
        r.commit("fix(w7p1): handle an empty body")
        r.commit("test(w7p2)!: a first test suite (#12)")
        ps, _, _ = labels(r, 7)
        self.assertEqual([(p[0], p[1]) for p in ps], [("1", "Add the stream endpoint"), ("2", "A first test suite")])

    def test_stages_are_s1_s2_with_titles_from_the_practical(self):
        r = Repo()
        r.commit("feat(w16s1): profile the raw tables")
        r.commit("feat(w16s2): load them")
        doc = os.path.join(r.dir, "practical.md")
        open(doc, "w").write("## Gate 0 - Setup\n## Stage 1 - Profile the data\n## Stage 2 - Load the raw tables\n## Stage 3 - Model\n")
        ps, up, _ = labels(r, 16, doc)
        self.assertEqual([(p[0], p[1]) for p in ps], [("S1", "Profile the data"), ("S2", "Load the raw tables")])
        self.assertEqual(up, [("S3", "not started")])

    def test_the_production_bridge_is_its_own_week(self):
        r = Repo()
        r.commit("feat(w11p3): last part of week 11")
        r.commit("feat(pf1p1): the lab skeleton")
        ps, _, base = labels(r, "PF1")
        self.assertEqual([p[0] for p in ps], ["1"])
        self.assertEqual((base["label"], base["title"]), ("W11", "where Week 11 ended"))
        self.assertTrue(base["base"])


class SeveralWeeksInOneRepo(unittest.TestCase):
    def test_later_work_never_changes_an_earlier_week(self):
        r = Repo()
        r.commit("Week 3 Part 1: transport")
        w3_end = r.commit("Week 3 Part 2: retries")
        r.commit("feat(w4p1): strict types")
        before = gitparts.parts(r.dir, 3)
        r.commit("feat(w18p1): aiofetch learns streaming")
        self.assertEqual(gitparts.parts(r.dir, 3), before)
        ps, _, base = labels(r, 18)
        self.assertEqual(base["label"], "W4")
        self.assertEqual(gitparts.parts(r.dir, 4)[2]["commit"], w3_end)  # week 4 starts where week 3 ended


class InProgress(unittest.TestCase):
    def test_the_newest_part_is_in_progress_until_main_has_it(self):
        r = Repo()
        r.commit("feat(w7p1): one")
        r.git("checkout", "-q", "-b", "w7p2")
        r.commit("feat(w7p2): two")
        ps, _, _ = labels(r, 7)
        self.assertEqual([(p[0], p[2]) for p in ps], [("1", False), ("2", True)])
        r.git("checkout", "-q", "main")
        r.git("merge", "-q", "--ff-only", "w7p2")
        ps, _, _ = labels(r, 7)
        self.assertEqual([(p[0], p[2]) for p in ps], [("1", False), ("2", False)])


if __name__ == "__main__":
    unittest.main()
