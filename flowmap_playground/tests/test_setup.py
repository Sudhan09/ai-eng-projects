"""Any function of yours, with what it needs. A method needs its object and a parameter you left out needs a value; the
playground tries, in order: 1. a test that reaches the function (your values go in as it starts), 2. your code that calls
it (the shortest way from a function that needs nothing), 3. built from type hints (forward chaining over the builders),
4. it asks you, and keeps your answer until Clear.

tests/sample_setup is a tiny shop with each awkward case; the real weeks (W4, W5) are checked too. Everything runs in
throwaway folders. run: python3 -m unittest flowmap_playground/tests/test_setup.py
"""

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLAYGROUND = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PLAYGROUND, "src", "flowmap_playground"))
sys.path.insert(0, HERE)
import server  # noqa: E402
import index  # noqa: E402
import flowmap  # noqa: E402
import pickruns  # noqa: E402
from test_shrink import fingerprints, untouched  # noqa: E402

SAMPLE = os.path.join(HERE, "sample_setup")
AUTO = os.path.join(PLAYGROUND, "drivers", "_auto.py")


def project_python():
    """A project's own Python that has pytest (the sample's tests run with it)."""
    for cfg in sorted(glob.glob(os.path.join(server.TESTS_MAP, "cfg", "*.py"))):
        c = flowmap.load(cfg)
        py = c.get("PYTHON") or os.path.join(c["REPO"], ".venv", "bin", "python")
        if os.path.exists(py) and subprocess.run([py, "-c", "import pytest"], capture_output=True).returncode == 0:
            return py
    return None


PY = project_python()


def end(d):
    """What the run's function gave back (a plain value), or how it ended."""
    r = d.get("returned") or next((e["value"] for e in d["events"] if e["k"] == "return" and e["fn"].startswith("test_playground.")), None)
    return r.get("v", r.get("t")) if r else d["status"]


@unittest.skipUnless(PY, "no project Python with pytest")
class Sample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="flowmap-setup-")
        cls.export = os.path.join(cls.home, "shop")
        shutil.copytree(SAMPLE, cls.export, ignore=shutil.ignore_patterns("__pycache__"))
        cls.ix = index.Index(cls.export)
        out = os.path.join(cls.home, "harvest.json")
        subprocess.run([PY, server.HARVEST, cls.export, out], capture_output=True, text=True, timeout=120, env=pickruns.safe_env())
        cls.calls = json.load(open(out))["calls"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)

    def run_typed(self, typed, picks=()):
        plans = server.setups(self.ix, typed, lambda: self.calls, [], list(picks))
        out = os.path.join(self.home, "run.json")
        d, yours, plan = server.run_plans(self.export, PY, f"play:{AUTO}:1:call", typed, plans, pickruns.safe_env(), out)
        return d, plan, [e for e in d["events"] if e["k"] in ("call", "new")]

    def test_1_a_test_that_reaches_it_and_your_value_goes_in(self):
        d, plan, calls = self.run_typed('models.MemoryStore.get("b")')
        self.assertEqual((plan["how"], plan["via"]), ("test", "tests/test_shop.py::test_store_keeps_a_value"))
        start = calls[1]
        self.assertEqual((calls[0]["fn"], start["fn"], dict(start["args"])["key"]["v"]), ("test_playground.test_store_keeps_a_value", "models.MemoryStore.get", "b"))
        self.assertEqual(end(d), 0)  # the test's store has only "a"

    def test_1_a_decorator_without_wraps_starts_at_your_method(self):
        d, plan, calls = self.run_typed('models.Shelf.price("ink")')
        self.assertEqual((plan["how"], plan["via"]), ("test", "tests/test_shop.py::test_shelf_prices_by_length"))
        self.assertEqual((calls[1]["fn"], dict(calls[1]["args"])["item"]["v"], end(d)), ("models.Shelf.price", "ink", 3))

    def test_1_an_inherited_init_from_the_test_that_makes_that_class(self):
        d, plan, calls = self.run_typed("models.OutOfStock()")
        self.assertEqual((plan["how"], plan["via"]), ("test", "tests/test_shop.py::test_out_of_stock_names_the_item"))
        self.assertEqual(calls[1]["fn"], "models.OutOfStock")

    def test_1_a_dataclass_a_test_makes(self):
        d, plan, calls = self.run_typed('models.Order("ink")')
        self.assertEqual((plan["how"], plan["via"]), ("test", "tests/test_shop.py::test_an_order_counts"))
        self.assertEqual((calls[1]["fn"], {k: v.get("v") for k, v in calls[1]["args"]}), ("models.Order", {"item": "ink", "n": 2}))

    def test_1_a_shared_init_starts_when_it_makes_that_class(self):
        d, plan, calls = self.run_typed("models.SoldOut()")
        self.assertEqual((plan["via"], calls[1]["fn"]), ("tests/test_shop.py::test_sold_out_after_a_miss", "models.SoldOut"))

    def test_1_a_test_that_makes_a_subclass_is_not_used_for_the_class(self):
        with self.assertRaises(server.NeedsSetup) as caught:  # its only test makes an OutOfStock, not a ShopError
            self.run_typed("models.ShopError()")
        self.assertEqual(caught.exception.ask, [{"fn": "models.ShopError", "name": "item", "type": None}])

    def test_1_a_test_that_calls_it_directly_comes_first(self):
        d, plan, calls = self.run_typed('jobs.weigh("ink")')
        self.assertEqual((plan["via"], calls[1]["fn"], end(d)), ("tests/test_shop.py::test_weigh_directly", "jobs.weigh", 6))  # "ink" in, the test's scale (2)

    def test_1_a_test_too_long_to_step_through_gives_way_to_the_next(self):
        d, plan, calls = self.run_typed("jobs.tally(scale=2)")
        self.assertEqual((plan["via"], end(d)), ("tests/test_shop.py::test_tally_two", 12))

    def test_2_your_code_that_calls_it(self):
        d, plan, calls = self.run_typed("jobs.report(limit=2)")
        self.assertEqual((plan["how"], plan["via"]), ("caller", "jobs.nightly → jobs.report"))
        self.assertEqual([c["fn"] for c in calls], ["test_playground.run_call", "jobs.report"])  # nightly ran, unrecorded
        self.assertEqual({k: v.get("v", v.get("n")) for k, v in calls[1]["args"]}, {"rows": 3, "limit": 2})
        self.assertEqual(end(d), 2)

    def test_3_built_from_type_hints_with_a_fake_for_the_interface(self):
        d, plan, calls = self.run_typed('models.Cart.add("pen", 2)')
        self.assertEqual(plan["how"], "built")
        self.assertEqual(plan["via"], "models.Cart.open(settings=models.get_settings(), store=models.FakeStore()).add(item='pen', n=2)")
        self.assertEqual(calls[1]["fn"], "models.Cart.add")  # the building isn't recorded: START is your call
        self.assertEqual(end(d), 2)

    def test_3_an_enum_from_its_first_member(self):
        d, plan, calls = self.run_typed("models.pack()")
        self.assertEqual((plan["via"], end(d)), ("models.pack(size=models.Size.S)", "S"))

    def test_3_an_async_method(self):
        d, plan, calls = self.run_typed("models.Cart.total()")
        self.assertEqual((plan["how"], calls[1]["fn"], end(d)), ("built", "models.Cart.total", 0.0))

    def test_3_your_value_and_a_built_one_together(self):
        d, plan, _ = self.run_typed('models.checkout(coupon="SAVE")')
        self.assertEqual((plan["how"], end(d)), ("built", "shop:SAVE"))

    def test_4_a_value_nothing_makes_is_asked_for(self):
        with self.assertRaises(server.NeedsSetup) as caught:
            self.run_typed("models.checkout()")
        self.assertEqual(caught.exception.ask, [{"fn": "models.checkout", "name": "coupon", "type": None}])

    def test_4_asked_when_the_code_that_calls_it_never_gets_there(self):
        with self.assertRaises(server.NeedsSetup) as caught:
            self.run_typed("jobs.audit()")
        self.assertEqual(caught.exception.ask, [{"fn": "jobs.audit", "name": "entries", "type": None}])
        self.assertIn("jobs.weekly → jobs.audit", str(caught.exception))

    def test_4_two_classes_that_need_each_other(self):
        with self.assertRaises(server.NeedsSetup) as caught:
            self.run_typed("models.Hen.lay()")
        self.assertEqual(caught.exception.ask, [{"fn": "models.Hen.lay", "name": "self", "type": "models.Hen"}])

    def test_4_a_type_from_outside_your_code(self):
        with self.assertRaises(server.NeedsSetup) as caught:
            self.run_typed("jobs.needs_db()")
        self.assertEqual(caught.exception.ask, [{"fn": "jobs.needs_db", "name": "conn", "type": None}])

    def test_4_your_answer_is_used(self):
        d, plan, _ = self.run_typed("models.checkout()", picks=[{"fn": "models.checkout", "name": "coupon", "value": '"VIP"', "pick": True}])
        self.assertEqual((plan["how"], end(d)), ("built", "shop:VIP"))

    def test_a_context_manager_you_type_is_entered(self):
        d, plan, _ = self.run_typed('jobs.use(jobs.opened("x"))')
        self.assertEqual((plan, end(d)), (None, "HANDLE:X"))

    def test_a_call_with_everything_given_runs_as_typed(self):
        d, plan, calls = self.run_typed('jobs.report(["a"], 5)')
        self.assertEqual((plan, [c["fn"] for c in calls], end(d)), (None, ["test_playground.run_call", "jobs.report"], 1))

    def test_a_function_behind_lru_cache_can_be_called(self):
        d, plan, calls = self.run_typed("models.shared_settings()")
        self.assertEqual((plan, [c["fn"] for c in calls][1:]), (None, ["models.shared_settings", "models.Settings"]))

    def test_an_inherited_init_with_your_value(self):
        d, plan, calls = self.run_typed('models.OutOfStock("pen")')
        self.assertEqual((plan, calls[1]["fn"], dict(calls[1]["args"])["item"]["v"]), (None, "models.OutOfStock", "pen"))

    def test_a_class_with_no_code_of_its_own_runs_none_of_yours(self):
        for typed in ('models.Closed("x")', "models.Size(2)"):
            d, plan, calls = self.run_typed(typed)
            self.assertEqual((plan, [c["fn"] for c in calls], d["status"]), (None, ["test_playground.run_call"], "passed"), typed)
        self.assertEqual(self.ix.params("models.Size"), [("value", None)])
        self.assertFalse(self.ix.runs_code("models.Closed"))

    def test_only_your_code_can_be_called(self):
        for typed in ('jobs.report(__import__("os").getcwd())', "models.MemoryStore()._secret()", 'os.system("x")',
                      "jobs.use(models.Size.__class__)", "jobs.use(models.MemoryStore.get)", "jobs.use(os.environ)"):
            d, plan, calls = self.run_typed(typed)
            self.assertEqual([c["fn"] for c in calls], ["test_playground.run_call"], typed)
            self.assertTrue(d["status"].startswith("raised ValueError"), (typed, d["status"]))


class RealWeeks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="flowmap-setup-weeks-")
        os.symlink(os.path.join(PLAYGROUND, "drivers"), os.path.join(cls.home, "drivers"))
        server.HERE = cls.home
        cls.found = server.projects(only=("W4", "W5"))
        cls.before = fingerprints(cls.found)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)

    def test_w4_a_method_gets_its_client_from_a_test(self):
        d = server.play(self.found["W4"], "5", "call", "client.AiofetchClient.get_item(1500)")
        calls = [e for e in d["events"] if e["k"] in ("call", "new")]
        self.assertEqual(d["setup"]["how"], "test")
        self.assertEqual((calls[1]["fn"], dict(calls[1]["args"])["item_id"]["v"]), ("client.AiofetchClient.get_item", 1500))
        self.assertEqual(d["returned"]["t"], "ItemMissing")

    def test_w5_load_with_your_value_inside_its_test(self):
        d = server.play(self.found["W5"], "1", "call", "lab.load(requests=3)")
        load = next(e for e in d["events"] if e["k"] == "call" and e["fn"] == "lab.load")
        self.assertEqual((d["setup"]["how"], dict(load["args"])["requests"]["v"], d["returned"]["n"]), ("test", 3, 3))

    def test_w5_a_function_its_own_module_hides_says_so(self):
        with self.assertRaises(ValueError) as caught:  # main() in __init__.py, and main.py
            server.play(self.found["W5"], "1", "call", "__init__.main()")
        self.assertIn("your module main.py has the same name and hides it", str(caught.exception))

    def test_the_saved_run_keeps_how_it_was_set_up(self):
        server.record("W5", self.found["W5"], "1", "call", "lab.load(requests=3)")
        saved = server.saved_runs("W5")[-1]
        self.assertEqual(saved["setup"]["how"], "test")

    def test_z_your_code_and_its_copies_are_untouched(self):
        untouched(self, self.before, self.found)


@unittest.skipUnless(shutil.which("google-chrome") and shutil.which("node"), "needs Chrome and node")
class SetupInPage(unittest.TestCase):
    """The real page: the note says how a function was set up; a piece nothing makes is asked for, used, then cleared."""

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="flowmap-setuppage-")
        os.symlink(os.path.join(PLAYGROUND, "drivers"), os.path.join(cls.home, "drivers"))
        server.HERE = cls.home
        cls.srv = server.serve(0, only=("W2", "W4"), suggest=False)
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}/"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.home, ignore_errors=True)

    def node(self, script, *args):
        r = subprocess.run(["node", os.path.join(HERE, script), self.url, *args], capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-800:])
        return r.stdout

    def test_the_note_says_which_test_set_it_up(self):
        line = self.node("run_in_page.mjs", "W4", "call", "client.AiofetchClient.get_item(1500)")
        self.assertIn('caption "■ END ↩ ItemMissing"', line)
        self.assertIn('note "set up by test_get_item_returns_the_shape_the_server_sent, your values in"', line)

    def test_a_piece_nothing_makes_is_asked_for_used_and_cleared(self):
        asked, ran, cleared = json.loads(self.node("ask_in_page.mjs", "W2", "4", "batch.checksum()", '"abc"'))["steps"]
        self.assertIn("batch.checksum needs payload", asked["said"])
        self.assertEqual([(r["name"], r["value"]) for r in asked["rows"]], [("batch.checksum · payload", "")])
        self.assertTrue(ran["run"].startswith("batch.checksum() · "), ran["run"])
        self.assertIn("END ↩", ran["caption"])
        self.assertEqual([(r["name"], r["value"], "mine" in r["cls"]) for r in ran["rows"]], [("batch.checksum · payload", '"abc"', True)])
        self.assertEqual(ran["rows"][0]["why"], "what you gave it, for every run of this week")
        self.assertEqual((cleared["rows"], cleared["clear"]), ([], False))
        self.assertEqual(server.week_changes("W2"), [])


if __name__ == "__main__":
    unittest.main()
