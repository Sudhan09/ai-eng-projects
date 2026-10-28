"""No recorded run kept in git holds a path from this machine (your username, a temp folder): runs/ is synced to GitHub."""

import glob
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL = re.compile(r"(?<![\w.])(/home/[^/\s\"]+/|/Users/[^/\s\"]+/|/tmp/claude|[A-Za-z]:\\\\Users\\\\)|-home-[a-z]")


class Runs(unittest.TestCase):
    def test_no_recorded_run_holds_a_local_path(self):
        found = []
        for path in sorted(glob.glob(os.path.join(ROOT, "runs", "**", "*.json"), recursive=True)):
            with open(path, encoding="utf-8") as f:
                m = LOCAL.search(f.read())
            if m:
                found.append(f"{os.path.relpath(path, ROOT)}: {m.group(0)}")
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
