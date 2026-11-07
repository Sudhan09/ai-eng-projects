"""The git hooks: installed fresh, rewritten when they point at another flowmap folder, left alone when up to date."""

import atexit
import os
import shutil
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
        stale = flowmap.HOOK.format(root=OLD).replace("flowmap_tests/src/flowmap_tests/flowmap.py hook", "flowmap/tools/flowmap.py hook")
        open(os.path.join(r.dir, ".git", "hooks", "post-commit"), "w").write(stale + "echo my own line\n")
        flowmap.install_hooks(r.dir, NEW)
        text = hooks(r)["post-commit"]
        self.assertNotIn(OLD + "/", text)
        self.assertEqual(text.count(f"python3 {NEW}/src/flowmap_tests/flowmap.py note"), 1)
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


# the hook text flowmap/ installed before it became flowmap_tests/ (git show ff53f1c:flowmap/tools/flowmap.py)
OLD_TEMPLATE = """#!/bin/sh
# flowmap: keep the project map up to date (installed by flowmap/tools/flowmap.py hook; delete this file to stop it)
python3 {root}/tools/flowmap.py note
( cd {root} && nohup python3 tools/flowmap.py update >> build/update.log 2>&1 & )
"""


def hook_command(tools):
    """`flowmap.py hook WX` run for real, from a sandbox whose src/flowmap_tests/ is `tools`, on a repo whose post-commit is the
    old one (pointing at a flowmap/ folder). Returns (what it printed, post-commit after, the sandbox, the old folder)."""
    import subprocess
    import tempfile
    r = Repo()
    box = tempfile.mkdtemp(prefix="flowmap-hookbox-")
    atexit.register(shutil.rmtree, box, True)  # gone when the tests end
    os.makedirs(os.path.join(box, "src"))
    os.symlink(tools, os.path.join(box, "src", "flowmap_tests"))
    os.makedirs(os.path.join(box, "cfg"))
    open(os.path.join(box, "cfg", "wx.py"), "w").write(f'KEY, NAME, WEEK = "WX", "x", "WX"\nREPO = {r.dir!r}\nWEEK_NUM, PRACTICAL = 9, None\n')
    old = os.path.join(os.path.dirname(box), "flowmap")
    open(os.path.join(r.dir, ".git", "hooks", "post-commit"), "w").write(OLD_TEMPLATE.format(root=old))
    out = subprocess.run([sys.executable, os.path.join(box, "src", "flowmap_tests", "flowmap.py"), "hook", "WX"], capture_output=True, text=True).stdout
    return out, open(os.path.join(r.dir, ".git", "hooks", "post-commit")).read(), box, old


class OldFolder(unittest.TestCase):
    def test_hook_rewrites_a_post_commit_that_points_at_the_old_flowmap_folder(self):
        out, text, box, old = hook_command(os.path.join(os.path.dirname(HERE), "src", "flowmap_tests"))
        self.assertNotIn("already installed", out)
        self.assertIn("updated (it pointed at another flowmap folder)", out)
        self.assertNotIn(old + "/", text)
        self.assertEqual(text, flowmap.HOOK.format(root=box))


class Init(unittest.TestCase):
    def test_init_installs_the_hook_too(self):
        """A new week is one command: `init` writes its settings and installs the git hook (before the first build, so
        a first build that fails still leaves the hook)."""
        import subprocess
        import tempfile
        r = Repo()
        r.commit("feat(w9p1): a first part")
        box = tempfile.mkdtemp(prefix="flowmap-initbox-")
        self.addCleanup(shutil.rmtree, box, True)
        os.makedirs(os.path.join(box, "src"))
        os.symlink(os.path.join(os.path.dirname(HERE), "src", "flowmap_tests"), os.path.join(box, "src", "flowmap_tests"))
        os.makedirs(os.path.join(box, "cfg"))
        subprocess.run([sys.executable, os.path.join(box, "src", "flowmap_tests", "flowmap.py"), "init", "WX", r.dir, "--week", "9"],
                       capture_output=True, text=True, timeout=300)
        self.assertTrue(os.path.exists(os.path.join(box, "cfg", "wx.py")))
        for name, text in hooks(r).items():
            self.assertEqual(text, flowmap.HOOK.format(root=box), name)


class Update(unittest.TestCase):
    def test_update_refreshes_the_playground_after_the_map(self):
        """One commit updates both: the hook runs `update`, which rebuilds the tests map and then the playground
        (flowmap_playground/src/flowmap_playground/server.py --refresh, next to flowmap_tests)."""
        import tempfile
        done = []
        root, build, refresh = flowmap.ROOT, flowmap.build, flowmap.refresh_playground
        flowmap.ROOT = tempfile.mkdtemp(prefix="flowmap-updatebox-")
        self.addCleanup(shutil.rmtree, flowmap.ROOT, True)
        flowmap.build = lambda **kw: done.append("map")
        flowmap.refresh_playground = lambda log=print: done.append("playground")
        try:
            flowmap.update()
        finally:
            flowmap.ROOT, flowmap.build, flowmap.refresh_playground = root, build, refresh
            os.chdir(root)
        self.assertEqual(done, ["map", "playground"])

    def test_the_playground_step_runs_the_playground_next_to_the_map(self):
        import subprocess
        import tempfile
        workspace = tempfile.mkdtemp(prefix="flowmap-workspace-")
        self.addCleanup(shutil.rmtree, workspace, True)
        box = os.path.join(workspace, "flowmap_tests")
        os.makedirs(box)
        os.makedirs(os.path.join(box, "src"))
        os.symlink(os.path.join(os.path.dirname(HERE), "src", "flowmap_tests"), os.path.join(box, "src", "flowmap_tests"))
        play = os.path.join(workspace, "flowmap_playground", "src", "flowmap_playground")
        os.makedirs(play)
        open(os.path.join(play, "server.py"), "w").write(
            "import sys\nopen(__file__ + '.ran', 'w').write(' '.join(sys.argv[1:]))\nprint('playground up to date (W1)')\n")
        out = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {os.path.join(box, 'src', 'flowmap_tests')!r}); import flowmap; flowmap.refresh_playground()"],
                             capture_output=True, text=True, timeout=60).stdout
        self.assertEqual(open(os.path.join(play, "server.py.ran")).read(), "--refresh")
        self.assertIn("playground up to date (W1)", out)


if __name__ == "__main__":
    unittest.main()
