"""Tests for the browser editor's HTTP backend."""

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from swmc.server import Session                      # noqa: E402
from swmc.webui import WebUI, box_height, doc_json   # noqa: E402

SAMPLE = os.environ.get(
    "SWMC_SAMPLE",
    r"C:\Users\andry\Downloads\Complex Helicopter Gyro.xml",
)


def get(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def post(url, payload, timeout=10):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class WebTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="swmc-web-")
        self.path = os.path.join(self.tmp, "gyro.xml")
        shutil.copyfile(SAMPLE, self.path)
        self.session = Session(autosave=True, poll_interval=0.3)
        self.session.open(self.path)
        self.ui = WebUI(self.session, "127.0.0.1", 8900)
        self.base = self.ui.start().rstrip("/")

    def tearDown(self):
        self.ui.stop()
        self.session.watcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def edit(self, ops):
        return post(self.base + "/api/edit", {"ops": ops})


class TestStatic(WebTestCase):
    def test_index_is_served(self):
        with urllib.request.urlopen(self.base + "/") as r:
            body = r.read().decode("utf-8")
        self.assertIn("<svg id=\"canvas\"", body)
        self.assertIn("/static/app.js", body)

    def test_assets_exist(self):
        for name in ("app.js", "style.css"):
            with urllib.request.urlopen(self.base + "/static/" + name) as r:
                self.assertGreater(len(r.read()), 500)

    def test_path_traversal_is_blocked(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.base + "/static/..%2F..%2Fmodel.py")
        self.assertEqual(ctx.exception.code, 404)


class TestApi(WebTestCase):
    def test_types(self):
        t = get(self.base + "/api/types")
        self.assertEqual(len(t["components"]), 60)
        self.assertEqual(len(t["bridge"]), 10)
        f8 = t["components"]["36"]
        self.assertEqual(len(f8["inputs"]), 8)
        self.assertEqual(f8["inputs"][0]["dt_name"], "number")
        self.assertEqual([p["field"] for p in f8["properties"]], ["e"])

    def test_state_shape(self):
        d = get(self.base + "/api/state")
        self.assertEqual(len(d["components"]), 141)   # 124 + 17 bridge
        self.assertEqual(d["header"]["name"], "NOT ZE Helicopter gyro")
        self.assertTrue(all({"id", "type", "x", "y", "w", "h"} <= set(c)
                            for c in d["components"]))
        self.assertEqual(d["grid"], 0.25)
        # every wire resolves to a real component
        ids = {c["id"] for c in d["components"]}
        for w in d["wires"]:
            self.assertIn(w["from"], ids)
            self.assertIn(w["to"], ids)

    def test_box_height_grows_with_pins(self):
        self.assertEqual(box_height(1, 1), 0.5)
        self.assertEqual(box_height(8, 1), 2.0)

    def test_documents(self):
        out = get(self.base + "/api/documents")
        self.assertEqual(len(out["open"]), 1)
        self.assertEqual(out["open"][0]["path"], os.path.abspath(self.path))


class TestEditing(WebTestCase):
    def test_add_and_connect_roundtrip(self):
        d = self.edit([{"op": "add_component", "type": "const", "x": 30, "y": 30,
                        "properties": {"n": 4}}])
        new = max(d["components"], key=lambda c: c["id"])
        self.assertEqual(new["properties"]["n"]["value"], 4)

        d = self.edit([{"op": "add_component", "type": "abs", "x": 32, "y": 30}])
        dst = max(d["components"], key=lambda c: c["id"])
        d = self.edit([{"op": "connect", "target": dst["id"], "input": "in1",
                        "source": new["id"]}])
        wire = [w for w in d["wires"] if w["to"] == dst["id"]]
        self.assertEqual(len(wire), 1)
        self.assertEqual(wire[0]["from"], new["id"])
        self.assertEqual(wire[0]["index"], 0)

        # autosave put it on disk
        with open(self.path, encoding="utf-8") as fh:
            self.assertIn('<in1 component_id="%d"/>' % new["id"], fh.read())

    def test_version_advances_on_edit(self):
        v0 = get(self.base + "/api/state")["version"]
        d = self.edit([{"op": "add_component", "type": "add", "x": 1, "y": 1}])
        self.assertGreater(d["version"], v0)

    def test_move_batch(self):
        d = get(self.base + "/api/state")
        ids = [c["id"] for c in d["components"][:3]]
        before = {c["id"]: c["x"] for c in d["components"][:3]}
        d = self.edit([{"op": "move_component", "id": ids, "dx": 2, "dy": 0}])
        after = {c["id"]: c["x"] for c in d["components"] if c["id"] in before}
        for i in ids:
            self.assertAlmostEqual(after[i], before[i] + 2)

    def test_disallowed_op_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.edit([{"op": "save", "path": "/etc/passwd"}])
        self.assertEqual(ctx.exception.code, 400)

    def test_bad_edit_leaves_document_untouched(self):
        before = len(get(self.base + "/api/state")["components"])
        with self.assertRaises(urllib.error.HTTPError):
            self.edit([
                {"op": "add_component", "type": "add", "x": 1, "y": 1},
                {"op": "connect", "target": 999999, "input": "in1", "source": 1},
            ])
        self.assertEqual(len(get(self.base + "/api/state")["components"]), before)

    def test_call_tool_allowlist(self):
        out = post(self.base + "/api/call", {"tool": "validate"})
        self.assertTrue(out["result"]["ok"])
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            post(self.base + "/api/call", {"tool": "close"})
        self.assertEqual(ctx.exception.code, 400)

    def test_undo_via_tool(self):
        before = len(get(self.base + "/api/state")["components"])
        self.edit([{"op": "add_component", "type": "add", "x": 5, "y": 5}])
        out = post(self.base + "/api/call", {"tool": "undo"})
        self.assertEqual(len(out["state"]["components"]), before)

    def test_issues_surface_in_state(self):
        d = self.edit([{"op": "add_component", "type": "const", "x": 70, "y": 70}])
        num = max(d["components"], key=lambda c: c["id"])
        d = self.edit([{"op": "add_component", "type": "and", "x": 72, "y": 70}])
        gate = max(d["components"], key=lambda c: c["id"])
        d = self.edit([{"op": "connect", "target": gate["id"], "input": "in1",
                        "source": num["id"]}])
        warn = [i for i in d["issues"] if i["level"] == "warning"]
        self.assertTrue(any("expects" in i["message"] for i in warn))


class TestEvents(WebTestCase):
    def test_sse_pushes_on_edit(self):
        received = []
        stop = threading.Event()

        def listen():
            try:
                with urllib.request.urlopen(self.base + "/api/events", timeout=15) as r:
                    for raw in r:
                        line = raw.decode("utf-8").strip()
                        if line.startswith("data:"):
                            received.append(json.loads(line[5:].strip()))
                            stop.set()
                            return
            except Exception:
                stop.set()

        t = threading.Thread(target=listen, daemon=True)
        t.start()
        time.sleep(0.6)   # let the stream attach
        self.edit([{"op": "add_component", "type": "abs", "x": 11, "y": 11}])
        stop.wait(timeout=10)
        self.assertTrue(received, "no SSE event arrived")
        self.assertEqual(received[0]["reason"], "edit")

    def test_external_write_reaches_the_browser(self):
        received = []
        stop = threading.Event()

        def listen():
            try:
                with urllib.request.urlopen(self.base + "/api/events", timeout=20) as r:
                    for raw in r:
                        line = raw.decode("utf-8").strip()
                        if line.startswith("data:"):
                            ev = json.loads(line[5:].strip())
                            received.append(ev)
                            if ev["reason"] == "external":
                                stop.set()
                                return
            except Exception:
                stop.set()

        t = threading.Thread(target=listen, daemon=True)
        t.start()
        time.sleep(0.6)

        from swmc import Microprocessor
        doc = Microprocessor.load(self.path)
        doc.name = "renamed by the game"
        doc.save(self.path)

        stop.wait(timeout=15)
        self.assertTrue(any(e["reason"] == "external" for e in received),
                        "external write was not pushed: %r" % received)
        self.assertEqual(get(self.base + "/api/state")["header"]["name"],
                         "renamed by the game")


if __name__ == "__main__":
    unittest.main(verbosity=2)
