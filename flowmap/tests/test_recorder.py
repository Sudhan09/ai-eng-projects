"""The recorder on a tiny project (tests/sample): one test for each thing it must handle (tools/trace.py)."""

import glob
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import flowmap  # noqa: E402
import pickruns  # noqa: E402

SAMPLE = os.path.join(ROOT, "tests", "sample")


def project_python(*libs):
    """A project's own Python that has pytest (the recorder runs tests with it) and these libraries, or None."""
    for cfg in sorted(glob.glob(os.path.join(ROOT, "cfg", "*.py"))):
        c = flowmap.load(cfg)
        py = c.get("PYTHON") or os.path.join(c["REPO"], ".venv", "bin", "python")
        if os.path.exists(py) and subprocess.run([py, "-c", "; ".join(f"import {x}" for x in ("pytest", *libs))], capture_output=True).returncode == 0:
            return py
    return None


PY = project_python()
PY_HTTPX = project_python("httpx")
OUT = tempfile.mkdtemp(prefix="flowmap-rec-")


def record(name, file="tests/unit/test_core.py", py=None):
    out = os.path.join(OUT, name.replace("::", "__") + ".json")
    subprocess.run([py or PY, os.path.join(ROOT, "tools", "trace.py"), SAMPLE, f"{file}::{name}", out],
                   capture_output=True, text=True, timeout=90, env=pickruns.safe_env())
    d = json.load(open(out))
    d["text"] = open(out).read()
    d["calls"] = [e for e in d["events"] if e["k"] in ("call", "new")]
    return d


def fns(d):
    return [e["fn"] for e in d["calls"]]


@unittest.skipUnless(PY, "no project Python with pytest")
class Recorder(unittest.TestCase):
    def test_a_fixture_test_records_its_body_only(self):
        d = record("test_fixture")
        self.assertEqual(d["status"], "passed")
        self.assertEqual(fns(d), ["test_core.test_fixture", "core.make", "core.Item"])  # not the autouse make("setup")
        self.assertNotIn("pytest_pyfunc_call", d["text"])  # a conftest hook is pytest's, not the test's

    def test_parametrize_records_the_first_case(self):
        d = record("test_param")
        self.assertEqual([a[1]["v"] for e in d["calls"] if e["fn"] == "core.make" for a in e["args"]], ["ab"])

    def test_a_test_in_a_class_and_a_subpackage(self):
        d = record("TestGroup::test_in_class")
        self.assertEqual(fns(d), ["test_core.TestGroup.test_in_class", "adapters.alpha.shout"])

    def test_an_error_class_without_transient(self):
        d = record("test_error_without_transient")
        self.assertEqual(d["status"], "passed")
        throw = next(e for e in d["events"] if e["k"] == "throw")
        self.assertEqual(throw["exc"]["t"], "AppError")
        self.assertNotIn("transient", json.dumps(throw))

    def test_gather_and_taskgroup_get_a_lane_per_task(self):
        for name, n in (("test_gather", 2), ("test_taskgroup", 3)):
            d = record(name)
            tasks = [e for e in d["events"] if e["k"] == "task"]
            self.assertEqual([t["label"] for t in tasks], [f"T{i + 1}" for i in range(n)])
            by = {e["id"]: e["fn"] for e in d["calls"]}
            self.assertTrue(all(by[t["by"]] in ("core.both", "core.grouped") for t in tasks))
            self.assertEqual({e["task"] for e in d["calls"] if e["fn"] == "core.one"}, {t["label"] for t in tasks})

    def test_to_thread_gets_a_thread_lane_under_the_call_that_sent_it(self):
        d = record("test_thread")
        work = next(e for e in d["calls"] if e["fn"] == "core.slow_double")
        self.assertEqual(work["task"], "TH1")
        self.assertEqual(next(e["fn"] for e in d["calls"] if e["id"] == work["parent"]), "core.threaded")
        self.assertEqual(work["via"], "concurrent")  # the thread pool, never the recorder's own file

    def test_a_generator_yields_its_values(self):
        d = record("test_generator")
        self.assertEqual([e["value"]["v"] for e in d["events"] if e["k"] == "yield"], [1, 2])

    def test_the_network_is_refused_but_this_machine_is_not(self):
        self.assertEqual(record("test_network_refused")["status"], "passed")  # passes only while recording
        self.assertEqual(record("test_local_connection_works")["status"], "passed")

    def test_values_never_carry_a_local_path(self):
        d = record("test_tmp_path")
        self.assertEqual(d["status"], "passed")
        for bad in ("/tmp/", "/home/", "pytest-of-"):
            self.assertNotIn(bad, d["text"])

    def test_a_test_file_skipped_at_import_is_skipped(self):
        if PY_HTTPX == PY:
            self.skipTest("this project Python has httpx")
        self.assertEqual(record("test_mock_transport", "tests/unit/test_http.py")["status"], "skipped")

    @unittest.skipUnless(PY_HTTPX, "no project Python with httpx")
    def test_a_fake_transport_shows_its_real_handler(self):
        d = record("test_mock_transport", "tests/unit/test_http.py", PY_HTTPX)
        self.assertEqual(d["status"], "passed")
        self.assertIn("MockTransport(handler=flaky_api)", d["text"])


if __name__ == "__main__":
    unittest.main()
