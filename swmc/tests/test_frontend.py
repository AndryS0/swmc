"""Static checks on the browser assets.

There is no headless browser in this environment, so instead of pretending to
do an end-to-end UI test these checks catch the class of bug that actually
bites: a typo'd element id, a CSS class that was never defined, a JS syntax
error, or a tool name the backend will refuse.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from swmc.server import BATCH_OPS, TOOLS            # noqa: E402
from swmc.webui import ALLOWED_TOOLS                # noqa: E402

SAMPLE = os.environ.get(
    "SWMC_SAMPLE",
    r"C:\Users\andry\Downloads\Complex Helicopter Gyro.xml",
)

STATIC = os.path.join(ROOT, "swmc", "static")


def _read(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as fh:
        return fh.read()


HTML = _read("index.html")
CSS = _read("style.css")

#: Every script the page loads, in load order.
JS_FILES = re.findall(r'<script src="/static/([^"]+)"', HTML)
JS_SOURCE = {name: _read(name) for name in JS_FILES}
#: Third-party code, held to a different standard than our own.
VENDOR = [n for n in JS_FILES if n.startswith("vendor/")]
OURS = {n: s for n, s in JS_SOURCE.items() if n not in VENDOR}
#: Concatenated, because the scripts share one global scope in the browser.
JS = "\n".join(OURS.values())


class TestSyntax(unittest.TestCase):
    def test_all_scripts_are_loaded_and_present(self):
        for name in ("app.js", "lua.js", "luaapi.js", "vendor/luaparse.js"):
            self.assertIn(name, JS_FILES)
        # luaapi.js defines data the editor reads, and lua.js calls luaparse at
        # load time only through functions, but keeping the order explicit
        # documents the dependency.
        self.assertLess(JS_FILES.index("luaapi.js"), JS_FILES.index("lua.js"))
        self.assertLess(JS_FILES.index("vendor/luaparse.js"), JS_FILES.index("lua.js"))
        for name in JS_FILES:
            self.assertTrue(os.path.isfile(os.path.join(STATIC, name)), name)

    def test_vendored_parser_is_attributed_and_pinned(self):
        src = JS_SOURCE["vendor/luaparse.js"]
        head = src[:600]
        self.assertIn("luaparse", head)
        self.assertIn("MIT", head, "vendored code must carry its licence")
        self.assertIn("0.3.1", head, "the vendored version must be stated")
        self.assertIn("5.3", head, "record which Lua version this targets")
        # and the editor must actually ask for that version
        self.assertIn("luaVersion: '5.3'", JS_SOURCE["lua.js"])

    def test_lua_version_matches_the_game(self):
        """stormworks64.exe reports Lua 5.3; the parser must agree."""
        self.assertIn("luaVersion: '5.3'", JS_SOURCE["lua.js"])

    def test_js_parses(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not on PATH")
        for name in JS_FILES:
            p = subprocess.run([node, "--check", os.path.join(STATIC, name)],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, "%s: %s" % (name, p.stderr))

    def test_lua_logic(self):
        """Runs the shipped highlighter over the sample's real Lua script."""
        node = shutil.which("node")
        if not node:
            self.skipTest("node not on PATH")
        from swmc import Microprocessor
        doc = Microprocessor.load(SAMPLE)
        lua = [c for c in doc.components if c.type_id == 56]
        env = dict(os.environ)
        if lua:
            env["SWMC_SCRIPT"] = lua[0].properties()["script"]
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "lua_logic.js")
        p = subprocess.run([node, script], capture_output=True, text=True,
                           cwd=ROOT, env=env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("api entries", p.stdout)
        if lua:
            self.assertNotIn("SWMC_SCRIPT not set", p.stdout,
                             "the real-script checks did not run")

    def test_no_lookalike_letters_in_source(self):
        """A Cyrillic 'a' inside an identifier reads exactly like an ASCII one.

        Symbols are fine -- the UI uses arrows and an ellipsis -- so this only
        rejects non-ASCII *letters*, which is the class of typo that survives
        review and then fails at runtime.
        """
        import unicodedata
        for name, src in OURS.items():
            if name == "luaapi.js":
                continue          # carries Japanese wiki page titles on purpose
            bad = sorted({c for c in src
                          if ord(c) > 127 and unicodedata.category(c).startswith("L")})
            self.assertEqual(
                bad, [],
                "%s has non-ASCII letters %r (%s)"
                % (name, bad, ", ".join(unicodedata.name(c, "?") for c in bad)))

    def test_js_logic(self):
        """Runs the shipped app.js in a VM with a stub DOM; see frontend_logic.js."""
        node = shutil.which("node")
        if not node:
            self.skipTest("node not on PATH")
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "frontend_logic.js")
        # Hand the harness every real component name so the label-fitting check
        # is exhaustive rather than a hand-picked sample.
        from swmc.nodetypes import BRIDGE_TYPES, COMPONENT_TYPES
        names = sorted({t.name for t in COMPONENT_TYPES.values()}
                       | {t.name for t in BRIDGE_TYPES.values()})
        env = dict(os.environ, SWMC_NAMES=json.dumps(names))
        p = subprocess.run([node, script], capture_output=True, text=True,
                           cwd=ROOT, env=env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("checked %d names" % len(names), p.stdout)

    def test_html_tags_balance(self):
        void = {"meta", "link", "br", "hr", "img", "input", "path", "rect", "use"}
        stack = []
        for m in re.finditer(r"<(/?)([a-zA-Z][\w-]*)([^>]*?)(/?)>", HTML):
            closing, tag, attrs, selfclose = m.groups()
            tag = tag.lower()
            if tag in void or selfclose or tag == "!doctype":
                continue
            if closing:
                self.assertTrue(stack, "stray </%s>" % tag)
                self.assertEqual(stack.pop(), tag)
            else:
                stack.append(tag)
        self.assertEqual(stack, [], "unclosed: %r" % stack)

    def test_css_braces_balance(self):
        self.assertEqual(CSS.count("{"), CSS.count("}"))


class TestWiring(unittest.TestCase):
    def test_every_id_used_by_js_exists_in_html(self):
        html_ids = set(re.findall(r'id="([^"]+)"', HTML))
        js_ids = set(re.findall(r"\$\('([^']+)'\)", JS))
        missing = sorted(js_ids - html_ids)
        self.assertEqual(missing, [], "app.js reaches for missing ids: %r" % missing)

    def test_every_html_id_is_used(self):
        """Catches leftovers in the markup that nothing drives."""
        html_ids = set(re.findall(r'id="([^"]+)"', HTML))
        used = set(re.findall(r"\$\('([^']+)'\)", JS))
        used |= set(re.findall(r"#([A-Za-z][\w-]*)", CSS))
        used |= set(re.findall(r'url\(#([^)]+)\)', HTML))
        unused = sorted(html_ids - used)
        self.assertEqual(unused, [], "unused ids in index.html: %r" % unused)

    def test_css_classes_referenced_by_js_are_defined(self):
        defined = set(re.findall(r"\.([a-zA-Z][\w-]*)", CSS))
        used = set()
        for m in re.finditer(r"class:\s*'([^']+)'", JS):
            used |= set(m.group(1).split())
        for m in re.finditer(r"classList\.(?:add|remove|toggle)\('([^']+)'\)", JS):
            used.add(m.group(1))
        # template-built class strings, e.g. 'node' + (sel ? ' selected' : '')
        for m in re.finditer(r"class:\s*'([^']+)'\s*\+", JS):
            used |= set(m.group(1).split())
        missing = sorted(c for c in used - defined if c)
        self.assertEqual(missing, [], "classes used in JS but absent from CSS: %r" % missing)

    def test_every_signal_type_has_a_colour_and_a_name(self):
        """The canvas legend and the pin tooltips must use one vocabulary."""
        from swmc.nodetypes import DATA_TYPE
        backend = {str(k) for k in DATA_TYPE}
        colours = set(re.findall(r"(\d+):\s*'var\(--dt-[a-z]+\)'", JS))
        self.assertEqual(colours, backend, "DT_COLOR and DATA_TYPE disagree")

        block = re.search(r"const DT_NAME = \{(.*?)\};", JS, re.S).group(1)
        names = {k: v for k, v in re.findall(r"(\d+):\s*'([^']+)'", block)}
        self.assertEqual(
            names, {str(k): v for k, v in DATA_TYPE.items()},
            "DT_NAME in app.js must match DATA_TYPE in nodetypes.py")

    def test_signal_colours_are_defined_and_distinct(self):
        swatches = dict(re.findall(r"--dt-([a-z]+):\s*(#[0-9a-fA-F]{3,8});", CSS))
        swatches = {k: v.lower() for k, v in swatches.items()}
        used = set(re.findall(r"var\(--dt-([a-z]+)\)", JS))
        self.assertEqual(used, set(swatches),
                         "every --dt-* colour used by app.js must exist in style.css")
        self.assertEqual(len(set(swatches.values())), len(swatches),
                         "two signal types share a colour: %r" % swatches)

    def test_js_only_posts_allowed_batch_ops(self):
        ops = set(re.findall(r"op:\s*'([a-z_]+)'", JS))
        self.assertTrue(ops, "no ops found in app.js")
        bad = sorted(ops - BATCH_OPS)
        self.assertEqual(bad, [], "app.js sends ops the backend rejects: %r" % bad)

    def test_js_only_calls_allowed_tools(self):
        called = set(re.findall(r"tool\('([a-z_]+)'", JS))
        self.assertTrue(called)
        bad = sorted(called - ALLOWED_TOOLS)
        self.assertEqual(bad, [], "app.js calls tools the ui may not use: %r" % bad)

    def test_allowed_tools_all_exist(self):
        names = {t["name"] for t in TOOLS}
        missing = sorted(ALLOWED_TOOLS - names)
        self.assertEqual(missing, [], "ALLOWED_TOOLS names no such tool: %r" % missing)

    def test_fetch_routes_match_the_server(self):
        routes = set(re.findall(r"'(/api/[a-z_]+)'", JS))
        with open(os.path.join(ROOT, "swmc", "webui.py"), encoding="utf-8") as fh:
            src = fh.read()
        served = set(re.findall(r'route == "(/api/[a-z_]+)"', src))
        served |= set(re.findall(r'url\.path == "(/api/[a-z_]+)"', src))
        missing = sorted(routes - served)
        self.assertEqual(missing, [], "app.js calls unserved routes: %r" % missing)


class TestDataContract(unittest.TestCase):
    """The shapes app.js indexes into must be the shapes webui.py produces."""

    def setUp(self):
        from swmc.webui import doc_json, type_catalogue
        from swmc.server import Session
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="swmc-fe-")
        sample = os.environ.get(
            "SWMC_SAMPLE", r"C:\Users\andry\Downloads\Complex Helicopter Gyro.xml")
        path = os.path.join(self.tmp, "g.xml")
        shutil.copyfile(sample, path)
        self.session = Session(autosave=False, poll_interval=5)
        self.session.open(path)
        p, state = self.session.resolve(path)
        self.doc = doc_json(state, p)
        self.types = type_catalogue()

    def tearDown(self):
        self.session.watcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_component_keys(self):
        needed = {"id", "type", "bridge", "name", "label", "category", "x", "y",
                  "w", "h", "in_fields", "n_out", "properties", "inputs"}
        for c in self.doc["components"]:
            self.assertTrue(needed <= set(c), "missing %r" % (needed - set(c)))

    def test_wire_keys(self):
        for w in self.doc["wires"]:
            self.assertEqual({"to", "field", "index", "from", "out"}, set(w))

    def test_type_keys(self):
        for table in (self.types["components"], self.types["bridge"]):
            for t in table.values():
                self.assertTrue({"type", "name", "category", "inputs", "outputs",
                                 "properties", "link_fields"} <= set(t))
                for i in t["inputs"]:
                    self.assertTrue({"field", "label", "dt", "dt_name"} <= set(i))

    def test_wire_index_is_within_the_target_pin_count(self):
        by_id = {c["id"]: c for c in self.doc["components"]}
        for w in self.doc["wires"]:
            target = by_id[w["to"]]
            self.assertLess(w["index"], len(target["in_fields"]),
                            "wire %r points past the pins of #%d" % (w, w["to"]))

    def test_every_property_kind_has_a_ui_branch(self):
        """propField() in app.js must handle every kind the backend emits."""
        kinds = set()
        for table in (self.types["components"], self.types["bridge"]):
            for t in table.values():
                for p in t["properties"]:
                    kinds.add(p["kind"])
        handled = {"prop_num", "attr_int", "attr_float", "attr_str"}
        self.assertEqual(sorted(kinds - handled), [],
                         "propField has no branch for %r" % sorted(kinds - handled))

    def test_json_is_serialisable(self):
        json.dumps(self.doc)
        json.dumps(self.types)


if __name__ == "__main__":
    unittest.main(verbosity=2)
