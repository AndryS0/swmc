"""Run every example. They are documentation, so they must actually work."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")
sys.path.insert(0, ROOT)

SAMPLE = os.environ.get(
    "SWMC_SAMPLE",
    r"C:\Users\andry\Downloads\Complex Helicopter Gyro.xml",
)


def run(script, *args, timeout=60):
    env = dict(os.environ, PYTHONPATH=ROOT, PYTHONUTF8="1")
    return subprocess.run(
        [sys.executable, os.path.join(EXAMPLES, script), *args],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
        env=env, timeout=timeout)


class TestExamples(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="swmc-ex-")
        self.src = os.path.join(self.tmp, "sample.xml")
        shutil.copyfile(SAMPLE, self.src)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def out(self, name):
        return os.path.join(self.tmp, name)

    def assertRan(self, p, *must_contain):
        self.assertEqual(p.returncode, 0,
                         "exit %d\n--- stdout ---\n%s\n--- stderr ---\n%s"
                         % (p.returncode, p.stdout, p.stderr))
        self.assertEqual(p.stderr.strip(), "", p.stderr)
        for needle in must_contain:
            self.assertIn(needle, p.stdout)

    def test_all_examples_are_listed_in_the_readme(self):
        with open(os.path.join(EXAMPLES, "README.md"), encoding="utf-8") as fh:
            readme = fh.read()
        scripts = sorted(f for f in os.listdir(EXAMPLES) if f.endswith(".py"))
        self.assertTrue(scripts)
        for s in scripts:
            self.assertIn(s, readme, "%s is not mentioned in examples/README.md" % s)

    def test_01_inspect(self):
        p = run("01_inspect.py", self.src)
        self.assertRan(p, "components,", "validate:", "property sliders")

    def test_01_inspect_needs_an_argument(self):
        p = run("01_inspect.py")
        self.assertNotEqual(p.returncode, 0)

    def test_02_build_from_scratch(self):
        out = self.out("built.xml")
        p = run("02_build_from_scratch.py", out)
        self.assertRan(p, "wrote", "external pins")
        self.assertTrue(os.path.exists(out))

        from swmc import Microprocessor
        doc = Microprocessor.load(out)
        self.assertEqual(doc.name, "Throttle conditioner")
        self.assertEqual([i for i in doc.validate() if i["level"] == "error"], [])
        self.assertEqual(len(doc.io_pins), 2)
        # the circuit is actually wired, not just placed
        clamp = doc.find(type="clamp")[0]
        self.assertTrue(clamp.links().get("in1"))
        labels = {c.label for c in doc.components if c.label}
        self.assertEqual(labels, {"Gain", "Trim"})

    def test_03_edit_in_place_leaves_the_input_alone(self):
        out = self.out("edited.xml")
        with open(self.src, encoding="utf-8", newline="") as fh:
            before = fh.read()
        p = run("03_edit_in_place.py", self.src, out)
        self.assertRan(p, "wrote")
        with open(self.src, encoding="utf-8", newline="") as fh:
            self.assertEqual(fh.read(), before, "the input file was modified")

        from swmc import Microprocessor
        doc = Microprocessor.load(out)
        self.assertEqual([i for i in doc.validate() if i["level"] == "error"], [])

    def test_04_edit_lua_read_only(self):
        p = run("04_edit_lua.py", self.src)
        self.assertRan(p, "newlines survived the load: True")

    def test_04_edit_lua_rewrite(self):
        out = self.out("lua.xml")
        p = run("04_edit_lua.py", self.src, out)
        self.assertRan(p, "round-tripped byte for byte: True",
                       "tabs and newlines intact: True")

    def test_05_watch_demo(self):
        out = self.out("watched.xml")
        shutil.copyfile(self.src, out)
        p = run("05_watch.py", "--demo", out)
        self.assertRan(p, "watching", "modified")
        self.assertIn("after mark_self_write, events: []", p.stdout)

    def test_06_mcp_client(self):
        p = run("06_mcp_client.py", self.src)
        self.assertRan(p, "server: stormworks-microprocessor",
                       "valid : ok=True", "built :")


if __name__ == "__main__":
    unittest.main(verbosity=2)
