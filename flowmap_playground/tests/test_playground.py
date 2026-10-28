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
        cls.newest = {k: flowmap.part_list(p["c"])[-1]["label"] for k, p in cls.srv.projects.items()}

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        shutil.rmtree(cls.home, ignore_errors=True)

    def ask(self, body, token=None, host=None, url=None):
        req = urllib.request.Request((url or self.url) + "play", data=json.dumps(body).encode(), method="POST",
                                     headers={"X-Flowmap-Token": token or self.srv.token, "Content-Type": "application/json", **({"Host": host} if host else {})})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def play(self, key, entry, text, part=None):
        status, got = self.ask({"key": key, "part": part or self.newest[key], "entry": entry, "input": text})
        self.assertEqual(status, 200, got)
        return got["run"]

    def in_page(self, *args):
        r = subprocess.run(["node", os.path.join(HERE, "run_in_page.mjs"), self.url, *args], capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-500:])
        return r.stdout

    @staticmethod
    def returned(run, suffix):
        return [e for e in run["events"] if e["k"] == "return" and e["fn"].endswith(suffix)]

    # the browser first: a fresh page and an entry it has never seen (the hidden "you" frame arrives with the run)
    @unittest.skipUnless(BROWSER, "needs Chrome and node")
    def test_a_typed_input_plays_to_its_end_in_the_page(self):
        for entry, text, end in (("get_item", "1500", "ItemMissing"), ("main", "/v2/items/7", "↩ 0"), ("jsonl", "/items/1 /items/2 torn", "{rows, stats}")):
            self.assertIn(end, self.in_page("W4", entry, text))

    @unittest.skipUnless(BROWSER, "needs Chrome and node")
    def test_b_a_run_that_ends_by_raising_shows_it_as_its_end(self):
        self.assertIn("END ⚡ TransientError", self.in_page("W3", "get_json", "/items/7=503", "1"))

    @unittest.skipUnless(BROWSER, "needs Chrome and node")
    def test_b_a_suggested_input_on_an_older_part_fills_the_box_and_plays_there(self):
        out = self.in_page("W3", "-", "try:0", "1")  # W3 Part 1's first suggestion: get_json /items/7
        self.assertIn("W3 Part 1", out)
        self.assertIn("/items/7", out)

    @unittest.skipUnless(BROWSER, "needs Chrome and node")
    def test_c_a_part_with_nothing_to_run_says_so(self):
        week = self.srv.projects["W4"]["parts"]
        saved = week.pop("1")
        try:
            self.srv.page = server.page(self.srv.projects, self.srv.token)
            self.assertIn("Nothing to run at Part 1", self.in_page("W4", "-", "nothing", "1"))
            status, got = self.ask({"key": "W4", "part": "1", "entry": "fetch_many", "input": "/items/1"})
            self.assertEqual((status, got["error"]), (400, "Nothing to run at Part 1"))
        finally:
            week["1"] = saved
            self.srv.page = server.page(self.srv.projects, self.srv.token)

    @unittest.skipUnless(BROWSER, "needs Chrome and node")
    def test_d_arrow_keys_step_the_run_but_the_text_box_keeps_its_own(self):
        r = subprocess.run(["node", os.path.join(server.TESTS_MAP, "checks", "keys.mjs"), self.url + "#W4"], capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-500:])
        self.assertIn("ok in the playground text box", r.stdout)

    def test_a_run_uses_the_part_you_chose_and_its_own_entry(self):
        run = self.play("W3", "get_json", "/items/7", part="1")  # W3 Part 1: make_client + get_json, no client yet
        names = {e["fn"] for e in run["events"] if e["k"] in ("call", "new")}
        self.assertEqual(run["part"], "1")
        self.assertIn("transport.get_json", names)
        self.assertFalse(any(n.startswith("client.") for n in names))
        status, got = self.ask({"key": "W4", "part": "3", "entry": "jsonl", "input": "/items/1"})  # jsonl arrives in Part 4
        self.assertEqual((status, got["error"]), (400, "jsonl isn't in Part 3 yet"))

    def test_two_servers_each_keep_their_own_page_and_secret(self):
        other = server.serve(0)  # rebuilds the same build/ files, as a second server on your machine would
        threading.Thread(target=other.serve_forever, daemon=True).start()
        try:
            for srv in (self.srv, other):
                page = urllib.request.urlopen(f"http://127.0.0.1:{srv.server_port}/", timeout=30).read().decode()
                self.assertIn(srv.token, page)
            status, _ = self.ask({"key": "W4", "part": "5", "entry": "get_item", "input": "7"})  # the first still works
            self.assertEqual(status, 200)
        finally:
            other.shutdown()

    def test_only_its_own_page_can_ask(self):
        self.assertEqual(self.ask({"key": "W4", "part": "5", "entry": "main", "input": "/v2/items/7"}, token="wrong")[0], 403)
        self.assertEqual(self.ask({"key": "W4", "part": "5", "entry": "main", "input": "/v2/items/7"}, host="evil.example")[0], 403)
        self.assertEqual(self.ask({"key": "W4", "part": "5", "entry": "nope", "input": "x"})[0], 400)

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

    def test_w4_jsonl_fetches_writes_and_reads_the_rows_back(self):
        run = self.play("W4", "jsonl", "/items/1 /items/2")
        firsts = [next(e["i"] for e in run["events"] if e["k"] == "call" and e["fn"].endswith(f)) for f in
                  (".fetch_many", ".to_row", "storage.write_jsonl", "storage.read_jsonl")]
        self.assertEqual(firsts, sorted(firsts))  # in that order
        got = dict(run["returned"]["items"])
        self.assertEqual(got["rows"]["n"], 2)
        self.assertEqual(dict(got["stats"]["fields"]), {"records": {"t": "int", "v": 2}, "malformed": {"t": "int", "v": 0}})

    def test_w4_jsonl_torn_skips_the_half_line_and_counts_it(self):
        got = dict(self.play("W4", "jsonl", "/items/1 /items/2 torn")["returned"]["items"])
        self.assertEqual(got["rows"]["n"], 2)
        self.assertEqual(dict(got["stats"]["fields"])["malformed"], {"t": "int", "v": 1})

    def test_w1_w2_w3_run_too(self):
        self.assertEqual(self.play("W1", "cli", "--level WARNING")["exit"], 0)
        self.assertEqual(self.play("W2", "cli", "--jobs 5 --fail-every 3")["exit"], 0)
        self.assertEqual(self.returned(self.play("W3", "fetch_many", "/items/1 /items/3=404"), ".fetch_many")[-1]["value"]["n"], 2)

    def test_too_long_or_wrong_inputs_say_why(self):
        status, got = self.ask({"key": "W2", "part": "5", "entry": "cli", "input": "--jobs 300"})
        self.assertEqual(status, 400)
        self.assertIn("too long", got["error"])
        status, got = self.ask({"key": "W4", "part": "5", "entry": "get_item", "input": "abc"})
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
