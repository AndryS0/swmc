"""End-to-end tests: drive the MCP server over real stdio, as a client would."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SAMPLE = os.environ.get(
    "SWMC_SAMPLE",
    r"C:\Users\andry\Downloads\Complex Helicopter Gyro.xml",
)


class Client:
    """Minimal MCP client over the server's stdin/stdout."""

    def __init__(self, *extra):
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "swmc.server", *extra],
            cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1,
        )
        self._id = 0

    def rpc(self, method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notify:
            self._id += 1
            msg["id"] = self._id
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        if notify:
            return None
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise AssertionError("server closed stdout; stderr:\n%s"
                                     % self.proc.stderr.read())
            resp = json.loads(line)
            if resp.get("id") == msg["id"]:
                return resp

    def call(self, tool, **args):
        resp = self.rpc("tools/call", {"name": tool, "arguments": args})
        if "error" in resp:
            raise AssertionError("rpc error: %s" % resp["error"])
        result = resp["result"]
        text = result["content"][0]["text"]
        if result.get("isError"):
            raise ToolFailure(text)
        # strip a leading conflict warning if present
        if not text.lstrip().startswith(("{", "[")):
            text = text.split("\n\n", 1)[1]
        return json.loads(text)

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=10)
        finally:
            for stream in (self.proc.stdout, self.proc.stderr):
                try:
                    stream.close()
                except Exception:
                    pass


class ToolFailure(Exception):
    pass


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="swmc-")
        self.path = os.path.join(self.tmp, "gyro.xml")
        shutil.copyfile(SAMPLE, self.path)
        self.c = Client()
        init = self.c.rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        })
        self.assertIn("result", init)
        self.init = init["result"]
        self.c.rpc("notifications/initialized", notify=True)

    def tearDown(self):
        self.c.close()
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestProtocol(ServerTestCase):
    def test_initialize(self):
        self.assertEqual(self.init["serverInfo"]["name"], "stormworks-microprocessor")
        self.assertEqual(self.init["protocolVersion"], "2024-11-05")
        self.assertTrue(self.init["capabilities"]["resources"]["subscribe"])

    def test_tools_list(self):
        resp = self.c.rpc("tools/list")
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}
        for expected in ("open", "add_component", "connect", "remove_component",
                         "move_component", "set_property", "poll_changes", "batch",
                         "validate", "undo"):
            self.assertIn(expected, names)
        for t in tools:
            self.assertIn("description", t)
            self.assertEqual(t["inputSchema"]["type"], "object")

    def test_unknown_method(self):
        resp = self.c.rpc("nope/nope")
        self.assertEqual(resp["error"]["code"], -32601)

    def test_ping(self):
        self.assertEqual(self.c.rpc("ping")["result"], {})

    def test_resources(self):
        self.c.call("open", path=self.path)
        res = self.c.rpc("resources/list")["result"]["resources"]
        self.assertEqual(len(res), 1)
        uri = res[0]["uri"]
        body = self.c.rpc("resources/read", {"uri": uri})["result"]
        self.assertTrue(body["contents"][0]["text"].startswith("<?xml"))


class TestCatalogue(ServerTestCase):
    def test_list_types(self):
        out = self.c.call("list_types")
        self.assertEqual(out["count"], 60)

    def test_list_types_filtered(self):
        out = self.c.call("list_types", category="composite")
        self.assertTrue(all(t["category"] == "composite" for t in out["types"]))
        out = self.c.call("list_types", query="pid")
        self.assertEqual({t["type"] for t in out["types"]}, {23, 39})

    def test_describe_type(self):
        out = self.c.call("describe_type", type="func8")
        self.assertEqual(out["type"], 36)
        self.assertEqual(len(out["inputs"]), 8)
        self.assertEqual(out["inputs"][0]["data_type"], "number")
        self.assertEqual([p["field"] for p in out["properties"]], ["e"])

    def test_describe_bridge_pin_types(self):
        out = self.c.call("list_types", bridge=True)
        self.assertEqual(out["count"], 10)


class TestEditingOverRpc(ServerTestCase):
    def test_open_and_summary(self):
        out = self.c.call("open", path=self.path)
        self.assertEqual(out["summary"]["components"], 124)
        self.assertTrue(out["autosave"])

    def test_add_connect_autosaves_to_disk(self):
        self.c.call("open", path=self.path)
        a = self.c.call("add_component", type="const", x=50, y=50,
                        properties={"n": 7})["added"]
        b = self.c.call("add_component", type="abs", x=52, y=50)["added"]
        self.c.call("connect", target=b["id"], input="in1", source=a["id"])
        # autosave means the change is already on disk
        with open(self.path, encoding="utf-8") as fh:
            disk = fh.read()
        self.assertIn('id="%d"' % a["id"], disk)
        self.assertIn('<in1 component_id="%d"/>' % a["id"], disk)

    def test_move_and_remove(self):
        self.c.call("open", path=self.path)
        c = self.c.call("add_component", type="add", x=1, y=1)["added"]
        self.c.call("move_component", id=c["id"], x=9, y=9)
        got = self.c.call("get_component", id=c["id"])
        self.assertEqual((got["pos"]["x"], got["pos"]["y"]), (9, 9))
        info = self.c.call("remove_component", id=c["id"])
        self.assertEqual(info["removed"], c["id"])
        with self.assertRaises(ToolFailure):
            self.c.call("get_component", id=c["id"])

    def test_move_many(self):
        self.c.call("open", path=self.path)
        a = self.c.call("add_component", type="add", x=1, y=1)["added"]
        b = self.c.call("add_component", type="add", x=2, y=1)["added"]
        out = self.c.call("move_component", id=[a["id"], b["id"]], dx=5, dy=0)
        self.assertEqual([m["x"] for m in out["moved"]], [6, 7])

    def test_set_property_batch_form(self):
        self.c.call("open", path=self.path)
        c = self.c.call("add_component", type="clamp", x=3, y=3)["added"]
        out = self.c.call("set_property", id=c["id"],
                          properties={"min": -5, "max": 5})
        self.assertEqual(out["properties"]["min"]["value"], -5)
        self.assertEqual(out["properties"]["max"]["value"], 5)

    def test_bad_property_is_tool_error_not_crash(self):
        self.c.call("open", path=self.path)
        c = self.c.call("add_component", type="add", x=3, y=4)["added"]
        with self.assertRaises(ToolFailure) as ctx:
            self.c.call("set_property", id=c["id"], field="nonsense", value=1)
        self.assertIn("no property", str(ctx.exception))

    def test_batch_is_atomic(self):
        self.c.call("open", path=self.path)
        before = self.c.call("summary")["components"]
        with self.assertRaises(ToolFailure):
            self.c.call("batch", operations=[
                {"op": "add_component", "type": "add", "x": 1, "y": 1},
                {"op": "add_component", "type": "totally-not-a-type"},
            ])
        self.assertEqual(self.c.call("summary")["components"], before)

    def test_batch_applies_all(self):
        self.c.call("open", path=self.path)
        out = self.c.call("batch", operations=[
            {"op": "add_component", "type": "const", "x": 60, "y": 60,
             "properties": {"n": 2}},
            {"op": "add_component", "type": "const", "x": 60, "y": 62,
             "properties": {"n": 3}},
            {"op": "add_component", "type": "mul", "x": 62, "y": 61},
        ])
        self.assertEqual(out["applied"], 3)
        ids = [r["result"]["added"]["id"] for r in out["results"]]
        self.c.call("batch", operations=[
            {"op": "connect", "target": ids[2], "input": 1, "source": ids[0]},
            {"op": "connect", "target": ids[2], "input": 2, "source": ids[1]},
        ])
        got = self.c.call("get_component", id=ids[2])
        self.assertEqual(got["inputs"], {"in1": ids[0], "in2": ids[1]})

    def test_undo_redo(self):
        self.c.call("open", path=self.path)
        before = self.c.call("summary")["components"]
        self.c.call("add_component", type="add", x=1, y=1)
        self.assertEqual(self.c.call("summary")["components"], before + 1)
        self.c.call("undo")
        self.assertEqual(self.c.call("summary")["components"], before)
        self.c.call("redo")
        self.assertEqual(self.c.call("summary")["components"], before + 1)

    def test_validate_and_trace(self):
        self.c.call("open", path=self.path)
        v = self.c.call("validate")
        self.assertTrue(v["ok"])
        pin = self.c.call("io_pins")["pins"][0]
        t = self.c.call("trace", id=pin["component_id"], direction="downstream", depth=2)
        self.assertEqual(t["root"], pin["component_id"])

    def test_raw_xml_escape_hatch(self):
        self.c.call("open", path=self.path)
        lua = self.c.call("list_components", type="lua")["components"][0]
        raw = self.c.call("raw_xml", id=lua["id"])
        self.assertIn("<c type=\"56\">", raw["xml"])
        self.assertIn("script=", raw["xml"])


class TestRealtime(ServerTestCase):
    def test_external_change_is_detected_and_reloaded(self):
        self.c.call("open", path=self.path)
        base = self.c.call("summary")["components"]

        # Simulate the game (or another editor) rewriting the file.
        sys.path.insert(0, ROOT)
        from swmc import Microprocessor
        doc = Microprocessor.load(self.path)
        doc.add("abs", 200, 200)
        doc.save(self.path)

        deadline = time.time() + 10
        events = []
        while time.time() < deadline:
            events = self.c.call("poll_changes")["events"]
            if events:
                break
            time.sleep(0.2)
        self.assertTrue(events, "watcher never reported the external write")
        self.assertEqual(events[0]["kind"], "modified")
        self.assertEqual(events[0].get("note"), "reloaded automatically")
        self.assertEqual(self.c.call("summary")["components"], base + 1)

    def test_our_own_writes_are_not_reported_as_external(self):
        self.c.call("open", path=self.path)
        self.c.call("poll_changes")
        self.c.call("add_component", type="abs", x=5, y=5)
        time.sleep(1.0)
        events = self.c.call("poll_changes")["events"]
        self.assertEqual(events, [], "autosave must not look like an external edit")

    def test_conflict_when_dirty(self):
        self.c.call("set_autosave", enabled=False)
        self.c.call("open", path=self.path)
        self.c.call("add_component", type="abs", x=7, y=7)   # dirty, not written

        sys.path.insert(0, ROOT)
        from swmc import Microprocessor
        other = Microprocessor.load(self.path)
        other.name = "changed elsewhere"
        other.save(self.path)

        deadline = time.time() + 10
        note = None
        while time.time() < deadline:
            evs = self.c.call("poll_changes")["events"]
            if evs:
                note = evs[0].get("note")
                break
            time.sleep(0.2)
        self.assertIsNotNone(note)
        self.assertIn("unsaved edits", note)
        with self.assertRaises(ToolFailure):
            self.c.call("save")
        out = self.c.call("save", force=True)
        self.assertEqual(out["saved"], os.path.abspath(self.path))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestGuiTools(ServerTestCase):
    def test_gui_opens_and_shares_the_document(self):
        import urllib.request, json as _json
        self.c.call("open", path=self.path)
        out = self.c.call("gui_open", port=8951, browser=False)
        self.assertTrue(out["url"].startswith("http://127.0.0.1:"))
        self.assertEqual(self.c.call("gui_status")["running"], True)

        # An edit made through MCP must be visible over the web API at once.
        added = self.c.call("add_component", type="abs", x=42, y=42)["added"]
        with urllib.request.urlopen(out["url"] + "api/state", timeout=10) as r:
            state = _json.loads(r.read().decode("utf-8"))
        self.assertIn(added["id"], [c["id"] for c in state["components"]])

        # ...and an edit made over the web API is visible to MCP.
        req = urllib.request.Request(
            out["url"] + "api/edit",
            data=_json.dumps({"ops": [{"op": "move_component", "id": added["id"],
                                       "x": 7, "y": 8}]}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
        got = self.c.call("get_component", id=added["id"])
        self.assertEqual((got["pos"]["x"], got["pos"]["y"]), (7, 8))

        self.assertEqual(self.c.call("gui_close")["running"], False)
