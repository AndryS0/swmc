"""Tests against the real 'Complex Helicopter Gyro' microprocessor."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swmc import Microprocessor, EditError, find_type, sxml  # noqa: E402
from swmc.nodetypes import BRIDGE_TYPES, COMPONENT_TYPES  # noqa: E402

SAMPLE = os.environ.get(
    "SWMC_SAMPLE",
    r"C:\Users\andry\Downloads\Complex Helicopter Gyro.xml",
)


def load():
    return Microprocessor.load(SAMPLE)


class TestParse(unittest.TestCase):
    def test_byte_exact_roundtrip(self):
        with open(SAMPLE, encoding="utf-8", newline="") as fh:
            original = fh.read()
        doc = Microprocessor.loads(original, SAMPLE)
        self.assertEqual(doc.to_string(), original,
                         "re-serialising an untouched document must be byte identical")

    def test_lua_script_survives(self):
        doc = load()
        lua = [c for c in doc.components if c.type_id == 56]
        self.assertTrue(lua, "sample should contain a Lua component")
        script = lua[0].properties()["script"]
        self.assertIn("\n", script)
        self.assertIn("\t", script)
        self.assertIn("function onTick()", script)

    def test_counts(self):
        doc = load()
        self.assertEqual(len(doc.components), 124)
        self.assertEqual(len(doc.bridge_components), 17)
        self.assertEqual(len(doc.io_pins), 17)

    def test_state_mirror_is_already_in_sync(self):
        """sync_states() must be a no-op on a file the game itself wrote."""
        with open(SAMPLE, encoding="utf-8", newline="") as fh:
            original = fh.read()
        doc = Microprocessor.loads(original, SAMPLE)
        doc.sync_states()
        self.assertEqual(doc.to_string(), original)

    def test_untyped_c_is_type_zero(self):
        doc = load()
        nots = [c for c in doc.components if c.type_id == 0]
        self.assertTrue(nots)
        self.assertEqual(nots[0].spec.name, "NOT")


class TestSchema(unittest.TestCase):
    def test_every_field_in_sample_is_modelled(self):
        """No attribute or child element in the sample may be unknown."""
        doc = load()
        unknown = []
        for comp in doc.all_components():
            spec = comp.spec
            known_links = set(spec.link_fields)
            for key in comp.object.attrib:
                if key == "id":
                    continue
                if spec.field_kind(key) is None:
                    unknown.append(("attr", comp.id, spec.name, key))
            for child in comp.object:
                if child.tag in ("pos", "items"):
                    continue
                if child.tag in known_links:
                    continue
                if spec.field_kind(child.tag) is None:
                    unknown.append(("child", comp.id, spec.name, child.tag))
        self.assertEqual(unknown, [], "unmodelled fields: %r" % (unknown[:10],))

    def test_type_36_shape(self):
        t = find_type(36)
        self.assertEqual(t.name, "f(x, y, z, w, a, b, c, d)")
        self.assertEqual(t.cls, "c_microprocessor_component_function_8_inputs")
        self.assertEqual(t.link_fields, ["in%d" % i for i in range(1, 9)])
        self.assertEqual(t.field_kind("e"), "attr_str")

    def test_variadic_composite_writer(self):
        t = find_type(40)
        names = t.link_fields
        self.assertEqual(names[0], "inc")
        self.assertEqual(names[1], "in1")
        self.assertEqual(names[32], "in32")
        self.assertEqual(names[-1], "inoff")

    def test_aliases_resolve(self):
        self.assertEqual(find_type("func8").type_id, 36)
        self.assertEqual(find_type("and").type_id, 1)
        self.assertEqual(find_type("Lua Script").type_id, 56)
        self.assertEqual(find_type(" 11 ").type_id, 11)

    def test_tables_complete(self):
        self.assertEqual(sorted(COMPONENT_TYPES), list(range(60)))
        self.assertEqual(sorted(BRIDGE_TYPES), list(range(10)))


class TestProvenance(unittest.TestCase):
    """The tables and the JSON reference must name the same build."""

    JSON = os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))),
        "stormworks_microprocessor_node_types.json")

    def source(self):
        import json
        with open(self.JSON, encoding="utf-8") as fh:
            return json.load(fh)["source"]

    def test_module_records_the_binary(self):
        from swmc.nodetypes import SOURCE
        self.assertEqual(SOURCE["game_version"], "v1.15.23")
        self.assertEqual(len(SOURCE["sha256"]), 64)
        self.assertEqual(SOURCE["sha256"], SOURCE["sha256"].lower())
        self.assertEqual(SOURCE["imagebase"], 0x140000000)
        self.assertEqual(SOURCE["lua_version"], "5.3")

    def test_json_and_module_agree(self):
        from swmc.nodetypes import SOURCE
        js = self.source()
        for key in ("game_version", "binary", "size_bytes", "sha256", "lua_version"):
            self.assertEqual(js[key], SOURCE[key], "%r differs between the JSON "
                             "reference and nodetypes.py" % key)
        self.assertEqual(js["imagebase"], hex(SOURCE["imagebase"]))

    def test_readmes_quote_the_same_hash(self):
        from swmc.nodetypes import SOURCE
        root = os.path.dirname(self.JSON)
        for path in (os.path.join(root, "README.md"),
                     os.path.join(root, "swmc", "README.md")):
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn(SOURCE["sha256"], text, "%s quotes a different hash" % path)
            self.assertIn(SOURCE["game_version"], text)

    def test_lua_editor_targets_the_embedded_lua(self):
        from swmc.nodetypes import SOURCE
        lua_js = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "swmc", "static", "lua.js")
        with open(lua_js, encoding="utf-8") as fh:
            self.assertIn("luaVersion: '%s'" % SOURCE["lua_version"], fh.read())


class TestEditing(unittest.TestCase):
    def test_add_component(self):
        doc = load()
        before = len(doc.components)
        c = doc.add("func8", 20, 5, properties={"e": "x+y*2"})
        self.assertEqual(len(doc.components), before + 1)
        self.assertEqual(c.type_id, 36)
        self.assertEqual(c.properties()["e"], "x+y*2")
        self.assertEqual(c.pos, (20.0, 5.0))
        self.assertEqual(c.id, 973)
        self.assertEqual(doc.root.get("id_counter"), "973")
        # a fresh id must never collide
        c2 = doc.add("add", 21, 5)
        self.assertNotEqual(c.id, c2.id)

    def test_add_then_reload_is_stable(self):
        doc = load()
        c = doc.add("clamp", 30, 30, properties={"min": -2, "max": 2})
        text = doc.to_string()
        again = Microprocessor.loads(text)
        got = again.get(c.id)
        self.assertEqual(got.type_id, 11)
        self.assertEqual(got.properties()["min"], {"text": "-2", "value": -2.0})
        self.assertEqual(got.properties()["max"], {"text": "2", "value": 2.0})

    def test_connect_and_disconnect(self):
        doc = load()
        a = doc.add("const", 40, 40, properties={"n": 5})
        b = doc.add("add", 42, 40)
        doc.connect(b.id, "in1", a.id)
        doc.connect(b.id, 2, a.id)
        self.assertEqual(b.links()["in1"]["component_id"], a.id)
        self.assertEqual(b.links()["in2"]["component_id"], a.id)
        self.assertTrue(doc.disconnect(b.id, "in2"))
        self.assertNotIn("in2", b.links())

    def test_connect_by_input_label(self):
        doc = load()
        src = doc.add("const", 50, 50)
        clamp = doc.add("clamp", 52, 50)
        doc.connect(clamp.id, "Input Number", src.id)
        self.assertEqual(clamp.links()["in1"]["component_id"], src.id)

    def test_link_elements_stay_in_serializer_order(self):
        doc = load()
        src = doc.add("const", 60, 60)
        f = doc.add("func8", 62, 60)
        for i in (5, 1, 3):
            doc.connect(f.id, i, src.id)
        order = [ch.tag for ch in f.object if ch.tag.startswith("in")]
        self.assertEqual(order, sorted(order, key=lambda t: int(t[2:])))

    def test_remove_clears_inbound_links(self):
        doc = load()
        src = doc.add("const", 70, 70)
        dst = doc.add("abs", 72, 70)
        doc.connect(dst.id, "in1", src.id)
        info = doc.remove(src.id)
        self.assertEqual(info["rewired_inputs"], 1)
        self.assertEqual(dst.links(), {})
        self.assertIsNone(doc.get(src.id, required=False))

    def test_remove_with_rewire_bridges_the_gap(self):
        doc = load()
        a = doc.add("const", 80, 80)
        mid = doc.add("abs", 82, 80)
        z = doc.add("abs", 84, 80)
        doc.connect(mid.id, "in1", a.id)
        doc.connect(z.id, "in1", mid.id)
        doc.remove(mid.id, rewire=True)
        self.assertEqual(z.links()["in1"]["component_id"], a.id)

    def test_remove_detaches_io_pin(self):
        doc = load()
        pin = doc.io_pins[0]
        info = doc.remove(pin["component_id"])
        self.assertIn(pin["id"], info["detached_pins"])
        self.assertEqual(len(doc.io_pins), 16)

    def test_move(self):
        doc = load()
        c = doc.components[0]
        doc.move(c.id, x=3, y=4)
        self.assertEqual(c.pos, (3.0, 4.0))
        doc.move(c.id, dx=0.5, dy=-1)
        self.assertEqual(c.pos, (3.5, 3.0))

    def test_move_many(self):
        doc = load()
        ids = [c.id for c in doc.components[:3]]
        before = {c.id: c.pos for c in doc.components[:3]}
        doc.move_many(ids, dx=2, dy=0)
        for c in doc.components[:3]:
            if c.id in before:
                self.assertAlmostEqual(c.pos[0], before[c.id][0] + 2)

    def test_zero_coordinate_is_omitted_like_the_game(self):
        doc = load()
        c = doc.add("abs", 0, 6)
        p = c.object.find("pos")
        self.assertNotIn("x", p.attrib)
        self.assertEqual(p.get("y"), "6")

    def test_set_property_rejects_unknown_field(self):
        doc = load()
        c = doc.add("add", 90, 90)
        with self.assertRaises(EditError):
            c.set_property("e", "x+1")

    def test_set_property_rejects_runtime_state(self):
        doc = load()
        c = doc.add("srlatch", 92, 90)
        with self.assertRaises(EditError):
            c.set_property("out1", 1)

    def test_prop_num_accepts_expression_text(self):
        doc = load()
        c = doc.add("const", 94, 90, properties={"n": {"text": "1/3", "value": 0.333333}})
        el = c.object.find("n")
        self.assertEqual(el.get("text"), "1/3")
        self.assertEqual(el.get("value"), "0.333333")

    def test_connect_unknown_input_raises(self):
        doc = load()
        c = doc.add("not", 96, 90)
        with self.assertRaises(EditError):
            c.connect("in2", 1)

    def test_connect_to_missing_source_raises(self):
        doc = load()
        c = doc.add("abs", 98, 90)
        with self.assertRaises(EditError):
            doc.connect(c.id, "in1", 999999)


class TestValidate(unittest.TestCase):
    def test_sample_has_no_errors(self):
        doc = load()
        errors = [i for i in doc.validate() if i["level"] == "error"]
        self.assertEqual(errors, [])

    def test_dangling_link_is_reported(self):
        doc = load()
        c = doc.add("abs", 100, 100)
        c.object.append(sxml.Element("in1", {"component_id": "424242"}))
        errors = [i for i in doc.validate() if i["level"] == "error"]
        self.assertTrue(any("424242" in i["message"] for i in errors))

    def test_type_mismatch_is_a_warning(self):
        doc = load()
        num = doc.add("const", 110, 110)       # outputs a number
        gate = doc.add("and", 112, 110)        # expects on/off
        doc.connect(gate.id, "in1", num.id)
        warnings = [i for i in doc.validate() if i["level"] == "warning"]
        self.assertTrue(any("expects" in i["message"] for i in warnings))

    def test_summary(self):
        doc = load()
        s = doc.summary()
        self.assertEqual(s["components"], 124)
        self.assertEqual(s["io_pins"], 17)
        self.assertIn("by_type", s)


class TestSave(unittest.TestCase):
    def test_save_and_reload(self):
        import tempfile
        doc = load()
        c = doc.add("func1", 120, 120, properties={"e": "x*2"})
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "out.xml")
            doc.save(out)
            again = Microprocessor.load(out)
            self.assertEqual(again.get(c.id).properties()["e"], "x*2")
            self.assertEqual(len(again.components), 125)
            # state mirror regenerated to match
            states = again.group.find("component_states")
            self.assertEqual(len(states.children), 125)
            self.assertEqual(states.children[-1].tag, "c124")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestWatcher(unittest.TestCase):
    """A manual poller and a background thread must not compete for events."""

    def setUp(self):
        import tempfile, shutil
        self.tmp = tempfile.mkdtemp(prefix="swmc-watch-")
        self.path = os.path.join(self.tmp, "w.xml")
        shutil.copyfile(SAMPLE, self.path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def touch(self):
        doc = Microprocessor.load(self.path)
        doc.add("abs", 90, 90)
        doc.save(self.path)

    def test_manual_watcher_starts_no_thread(self):
        from swmc.watch import FileWatcher
        w = FileWatcher(interval=0.2)
        w.watch(self.path)
        try:
            self.assertIsNone(w._thread, "a callback-less watcher must not poll "
                                         "in the background and steal events")
        finally:
            w.stop()

    def test_manual_polling_sees_every_change(self):
        from swmc.watch import FileWatcher
        w = FileWatcher(interval=0.2)
        w.watch(self.path)
        try:
            for _ in range(5):
                self.assertEqual(w.poll_once(), [])
                self.touch()
                events = w.poll_once()
                self.assertEqual(len(events), 1, "a change was swallowed")
                self.assertEqual(events[0]["kind"], "modified")
        finally:
            w.stop()

    def test_callback_watcher_runs_in_the_background(self):
        import time
        from swmc.watch import FileWatcher
        seen = []
        w = FileWatcher(interval=0.2, on_change=lambda evs: seen.extend(evs))
        w.watch(self.path)
        try:
            self.assertIsNotNone(w._thread)
            self.touch()
            deadline = time.time() + 8
            while time.time() < deadline and not seen:
                time.sleep(0.1)
            self.assertEqual(len(seen), 1)
        finally:
            w.stop()

    def test_self_writes_are_not_reported_back(self):
        from swmc.watch import FileWatcher
        w = FileWatcher(interval=0.2)
        w.watch(self.path)
        try:
            self.touch()
            w.mark_self_write(self.path)
            self.assertEqual(w.poll_once(), [])
        finally:
            w.stop()


class TestPublicApi(unittest.TestCase):
    """Guard rails for the surface other people would code against."""

    def test_every_public_member_is_documented(self):
        import inspect
        import swmc
        missing = []
        for name in swmc.__all__:
            obj = getattr(swmc, name)
            if inspect.isclass(obj):
                if not obj.__doc__:
                    missing.append(name)
                for n, v in vars(obj).items():
                    if n.startswith("_"):
                        continue
                    fn = v.fget if isinstance(v, property) else v
                    if callable(fn) and not getattr(fn, "__doc__", None):
                        missing.append("%s.%s" % (name, n))
            elif callable(obj) and not obj.__doc__:
                missing.append(name)
        self.assertEqual(missing, [], "undocumented public API: %r" % (missing,))

    def test_one_exception_base_covers_everything(self):
        from swmc import SwmcError, EditError, UnknownTypeError, find_type
        doc = load()
        for bad in (lambda: find_type("definitely-not-a-type"),
                    lambda: doc.get(10 ** 9),
                    lambda: doc.add("definitely-not-a-type"),
                    lambda: Microprocessor.new(width=99)):
            with self.assertRaises(SwmcError):
                bad()
        # and the type lookup still behaves like a mapping miss
        with self.assertRaises(KeyError):
            find_type("definitely-not-a-type")
        self.assertTrue(issubclass(UnknownTypeError, EditError))

    def test_container_protocol(self):
        doc = load()
        self.assertEqual(len(doc), len(doc.all_components()))
        first = doc.components[0]
        self.assertIn(first.id, doc)
        self.assertNotIn(10 ** 9, doc)
        self.assertEqual(doc[first.id].id, first.id)
        self.assertEqual(len([c for c in doc]), len(doc))

    def test_label_is_distinct_from_the_type_name(self):
        doc = load()
        slider = doc.find(type="slider")[0]
        self.assertTrue(slider.label)
        self.assertEqual(slider.spec.name, "Property Slider")
        self.assertNotEqual(slider.label, slider.spec.name)
        slider.label = "Renamed"
        self.assertEqual(slider.label, "Renamed")
        self.assertEqual(doc[slider.id].properties()["name"], "Renamed")

    def test_new_document_is_valid_and_round_trips(self):
        doc = Microprocessor.new("Fresh", "desc", width=3, length=2)
        self.assertEqual(doc.name, "Fresh")
        self.assertEqual(doc.size, (3, 2))
        self.assertEqual(len(doc), 0)
        self.assertEqual(doc.validate(), [])
        c = doc.add("add", 1, 1)
        again = Microprocessor.loads(doc.to_string())
        self.assertEqual(len(again), 1)
        self.assertEqual(again[c.id].spec.name, "Add")
        self.assertEqual(again.validate(), [])

    def test_new_rejects_an_impossible_size(self):
        from swmc import EditError
        for bad in ((0, 1), (7, 1), (1, 0), (1, 7)):
            with self.assertRaises(EditError):
                Microprocessor.new(width=bad[0], length=bad[1])

    def test_new_escapes_its_header_text(self):
        doc = Microprocessor.new(name='Quote " & <angle>', description="a & b")
        again = Microprocessor.loads(doc.to_string())
        self.assertEqual(again.name, 'Quote " & <angle>')
        self.assertEqual(again.description, "a & b")


class TestTyping(unittest.TestCase):
    """The package advertises inline types; keep that claim true."""

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def test_py_typed_marker_exists(self):
        marker = os.path.join(self.ROOT, "swmc", "py.typed")
        self.assertTrue(os.path.isfile(marker),
                        "py.typed is what makes the hints visible to consumers")

    def test_py_typed_ships_in_the_wheel(self):
        with open(os.path.join(self.ROOT, "pyproject.toml"), encoding="utf-8") as fh:
            pyproject = fh.read()
        self.assertIn('"py.typed"', pyproject,
                      "py.typed must be listed as package data or it is left out "
                      "of the built distribution")

    def test_public_api_is_annotated(self):
        import inspect
        import swmc
        unannotated = []
        for name in swmc.__all__:
            obj = getattr(swmc, name)
            targets = []
            if inspect.isclass(obj):
                for n, v in vars(obj).items():
                    if n.startswith("__"):
                        continue
                    fn = v.fget if isinstance(v, property) else v
                    if inspect.isfunction(fn):
                        targets.append(("%s.%s" % (name, n), fn))
            elif inspect.isfunction(obj):
                targets.append((name, obj))
            for label, fn in targets:
                sig = inspect.signature(fn)
                if sig.return_annotation is inspect.Signature.empty:
                    unannotated.append("%s -> ?" % label)
                for pname, p in sig.parameters.items():
                    if pname in ("self", "cls") or p.kind in (
                            p.VAR_POSITIONAL, p.VAR_KEYWORD):
                        continue
                    if p.annotation is inspect.Parameter.empty:
                        unannotated.append("%s(%s)" % (label, pname))
        self.assertEqual(unannotated, [],
                         "unannotated public API: %r" % (unannotated[:12],))

    def test_mypy_is_clean(self):
        """Run mypy if it is available; skipped otherwise."""
        import shutil
        import subprocess
        mypy = shutil.which("mypy")
        if not mypy:
            self.skipTest("mypy not installed")
        p = subprocess.run(
            [mypy, "--ignore-missing-imports",
             *[os.path.join(self.ROOT, "swmc", f) for f in
               ("errors.py", "sxml.py", "watch.py", "nodetypes.py", "model.py")]],
            capture_output=True, text=True, cwd=self.ROOT)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
