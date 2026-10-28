"""The git hooks: installed fresh, rewritten when they point at another flowmap folder, left alone when up to date."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_parts import Repo  # noqa: E402
from test_recorder import flowmap  # noqa: E402

NEW = "/home/me/ai_eng_workspace/flowmap_tests"
OLD = "/home/me/ai_eng_workspace/flowmap"


def hooks(repo):
    return {n: open(os.path.join(repo.dir, ".git", "hooks", n)).read() for n in ("post-commit", "post-merge")}


class Hooks(unittest.TestCase):
    def test_a_fresh_repo_gets_both_hooks(self):
        r = Repo()
        flowmap.install_hooks(r.dir, NEW)
        for name, text in hooks(r).items():
            self.assertEqual(text, flowmap.HOOK.format(root=NEW), name)
            self.assertTrue(os.access(os.path.join(r.dir, ".git", "hooks", name), os.X_OK))

    def test_a_hook_pointing_at_the_old_folder_is_rewritten_and_your_lines_stay(self):
        r = Repo()
        stale = flowmap.HOOK.format(root=OLD).replace("flowmap_tests/tools/flowmap.py hook", "flowmap/tools/flowmap.py hook")
        open(os.path.join(r.dir, ".git", "hooks", "post-commit"), "w").write(stale + "echo my own line\n")
        flowmap.install_hooks(r.dir, NEW)
        text = hooks(r)["post-commit"]
        self.assertNotIn(OLD + "/", text)
        self.assertEqual(text.count(f"python3 {NEW}/tools/flowmap.py note"), 1)
        self.assertIn("echo my own line", text)
        self.assertTrue(text.startswith("#!/bin/sh\n"))

    def test_an_up_to_date_hook_is_left_alone(self):
        r = Repo()
        flowmap.install_hooks(r.dir, NEW)
        path = os.path.join(r.dir, ".git", "hooks", "post-commit")
        open(path, "a").write("echo after ours\n")
        before = hooks(r)
        flowmap.install_hooks(r.dir, NEW)
        self.assertEqual(hooks(r), before)


# the hook text flowmap/ installed before it became flowmap_tests/ (git show 399797e:flowmap/tools/flowmap.py)
OLD_TEMPLATE = """#!/bin/sh
# flowmap: keep the project map up to date (installed by flowmap/tools/flowmap.py hook; delete this file to stop it)
python3 {root}/tools/flowmap.py note
( cd {root} && nohup python3 tools/flowmap.py update >> build/update.log 2>&1 & )
"""


def hook_command(tools):
    """`flowmap.py hook WX` run for real, from a sandbox whose tools/ is `tools`, on a repo whose post-commit is the
    old one (pointing at a flowmap/ folder). Returns (what it printed, post-commit after, the sandbox, the old folder)."""
    import subprocess
    import tempfile
    r = Repo()
    box = tempfile.mkdtemp(prefix="flowmap-hookbox-")
    os.symlink(tools, os.path.join(box, "tools"))
    os.makedirs(os.path.join(box, "cfg"))
    open(os.path.join(box, "cfg", "wx.py"), "w").write(f'KEY, NAME, WEEK = "WX", "x", "WX"\nREPO = {r.dir!r}\nWEEK_NUM, PRACTICAL = 9, None\n')
    old = os.path.join(os.path.dirname(box), "flowmap")
    open(os.path.join(r.dir, ".git", "hooks", "post-commit"), "w").write(OLD_TEMPLATE.format(root=old))
    out = subprocess.run([sys.executable, os.path.join(box, "tools", "flowmap.py"), "hook", "WX"], capture_output=True, text=True).stdout
    return out, open(os.path.join(r.dir, ".git", "hooks", "post-commit")).read(), box, old


class OldFolder(unittest.TestCase):
    def test_hook_rewrites_a_post_commit_that_points_at_the_old_flowmap_folder(self):
        out, text, box, old = hook_command(os.path.join(os.path.dirname(HERE), "tools"))
        self.assertNotIn("already installed", out)
        self.assertIn("updated (it pointed at another flowmap folder)", out)
        self.assertNotIn(old + "/", text)
        self.assertEqual(text, flowmap.HOOK.format(root=box))


if __name__ == "__main__":
    unittest.main()
