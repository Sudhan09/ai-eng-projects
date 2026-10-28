"""The playground end to end: the server (in a throwaway folder, never your runs/), each week's driver, the page.

run: python3 -m unittest discover -s flowmap_playground/tests
"""

import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PLAYGROUND = os.path.dirname(HERE)
sys.path.insert(0, PLAYGROUND)
import server  # noqa: E402
import flowmap  # noqa: E402  (flowmap_tests/tools, put on the path by server)

BROWSER = bool(shutil.which("google-chrome") and shutil.which("node"))


class Playground(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="flowmap-playground-")
        os.symlink(os.path.join(PLAYGROUND, "drivers"), os.path.join(cls.home, "drivers"))
        server.HERE = cls.home  # runs/ and build/ go here, not into your playground
        cls.srv = server.serve(0)
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}/"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        shutil.rmtree(cls.home, ignore_errors=True)

    def ask(self, body, token=None, host=None):
        req = urllib.request.Request(self.url + "play", data=json.dumps(body).encode(), method="POST",
                                     headers={"X-Flowmap-Token": token or server.TOKEN, "Content-Type": "application/json", **({"Host": host} if host else {})})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def play(self, key, entry, text):
        status, got = self.ask({"key": key, "entry": entry, "input": text})
        self.assertEqual(status, 200, got)
        return got["run"]

    @staticmethod
    def returned(run, suffix):
        return [e for e in run["events"] if e["k"] == "return" and e["fn"].endswith(suffix)]

    # the browser first: a fresh page and an entry it has never seen (the hidden "you" frame arrives with the run)
    @unittest.skipUnless(BROWSER, "needs Chrome and node")
    def test_a_typed_input_plays_to_its_end_in_the_page(self):
        for entry, text, end in (("get_item", "1500", "ItemMissing"), ("main", "/v2/items/7", "↩ 0")):
            r = subprocess.run(["node", os.path.join(HERE, "run_in_page.mjs"), self.url, "W4", entry, text], capture_output=True, text=True, timeout=300)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-500:])
            self.assertIn(end, r.stdout)

    def test_only_its_own_page_can_ask(self):
        self.assertEqual(self.ask({"key": "W4", "entry": "main", "input": "/v2/items/7"}, token="wrong")[0], 403)
        self.assertEqual(self.ask({"key": "W4", "entry": "main", "input": "/v2/items/7"}, host="evil.example")[0], 403)
        self.assertEqual(self.ask({"key": "W4", "entry": "nope", "input": "x"})[0], 400)

    def test_w4_main_prints_its_row_and_exits_0(self):
        run = self.play("W4", "main", "/v2/items/7")
        self.assertEqual((run["exit"], run["part"]), (0, "5"))
        self.assertIn('"url": "/v2/items/7"', run["printed"][0])
        self.assertTrue(self.returned(run, "settings.get_settings"))  # @lru_cache: still recorded

    def test_w4_get_item_1500_is_item_missing_and_3007_takes_the_detour(self):
        missing = self.play("W4", "get_item", "1500")
        self.assertEqual(self.returned(missing, ".get_item")[-1]["value"]["t"], "ItemMissing")
        moved = self.play("W4", "get_item", "3007")
        self.assertEqual(self.returned(moved, ".get_item")[-1]["value"]["t"], "ItemFound")
        self.assertEqual(sum(1 for e in moved["events"] if e["k"] == "call" and e["fn"] == "flaky.FlakyAPI.get"), 2)

    def test_w4_a_scripted_503_is_tried_three_times(self):
        run = self.play("W4", "main", "/items/1=503,503,200")
        self.assertEqual(sum(1 for e in run["events"] if e["k"] == "call" and e["fn"].endswith("._attempt")), 3)
        self.assertEqual(run["exit"], 0)

    def test_w1_w2_w3_run_too(self):
        self.assertEqual(self.play("W1", "cli", "--level WARNING")["exit"], 0)
        self.assertEqual(self.play("W2", "cli", "--jobs 5 --fail-every 3")["exit"], 0)
        self.assertEqual(self.returned(self.play("W3", "fetch_many", "/items/1 /items/3=404"), ".fetch_many")[-1]["value"]["n"], 2)

    def test_too_long_or_wrong_inputs_say_why(self):
        status, got = self.ask({"key": "W2", "entry": "cli", "input": "--jobs 300"})
        self.assertEqual(status, 400)
        self.assertIn("too long", got["error"])
        status, got = self.ask({"key": "W4", "entry": "get_item", "input": "abc"})
        self.assertEqual((status, got["error"]), (400, "get_item takes item ids, e.g. 7 1500 3007"))

    # last: flowmap_tests' page guards (START, END, steps, panels, words, local paths) on the page with every run above
    @unittest.skipUnless(BROWSER, "needs Chrome and node")
    def test_z_every_guard_passes_on_the_playground_page(self):
        build = os.path.join(self.home, "build")
        os.chdir(server.TESTS_MAP)
        subprocess.run([sys.executable, "tools/inject.py", "page/flowmap.html", os.path.join(build, "data.js"), os.path.join(build, "check.html"),
                        "--hook", "checks/smoke.js"], check=True, capture_output=True)
        dom = subprocess.run(["timeout", "900", "google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--window-size=1440,900",
                              "--virtual-time-budget=2500000", "--dump-dom", "file://" + os.path.join(build, "check.html")], capture_output=True, text=True).stdout
        m = re.search(r'<pre id="smoke">(.*?)</pre>', dom, re.S)
        self.assertTrue(m, "the page check did not run")
        self.assertEqual(flowmap.problems(html.unescape(m.group(1))), [])


if __name__ == "__main__":
    unittest.main()
