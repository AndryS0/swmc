"""Drive the MCP server over stdio, the way an agent does.

    python examples/06_mcp_client.py "Complex Helicopter Gyro.xml"

Useful for checking the server works outside Claude Code, and as a reference
for wiring it into some other MCP client. Operates on a temporary copy.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile


class Client:
    """The smallest MCP client that can hold a conversation."""

    def __init__(self):
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "swmc.server"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1,
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
                raise RuntimeError("server exited")
            resp = json.loads(line)
            if resp.get("id") == msg["id"]:
                if "error" in resp:
                    raise RuntimeError(resp["error"]["message"])
                return resp["result"]

    def call(self, tool, **args):
        res = self.rpc("tools/call", {"name": tool, "arguments": args})
        text = res["content"][0]["text"]
        if res.get("isError"):
            raise RuntimeError(text)
        if not text.lstrip().startswith(("{", "[")):   # a conflict banner
            text = text.split("\n\n", 1)[1]
        return json.loads(text)

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=10)
        self.proc.stdout.close()


def main(path):
    tmp = tempfile.mkdtemp(prefix="swmc-example-")
    work = os.path.join(tmp, os.path.basename(path))
    shutil.copyfile(path, work)

    c = Client()
    try:
        info = c.rpc("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "example", "version": "1"},
        })
        c.rpc("notifications/initialized", notify=True)
        print("server: %(name)s %(version)s" % info["serverInfo"])
        print("tools : %d" % len(c.rpc("tools/list")["tools"]))

        print("open  : %s" % c.call("open", path=work)["summary"]["name"])

        # Look a type up rather than hardcoding a number.
        f8 = c.call("describe_type", type="func8")
        print("type  : %d %s, %d inputs, property %r"
              % (f8["type"], f8["name"], len(f8["inputs"]),
                 f8["properties"][0]["field"]))

        # batch applies everything under one undo step, and rolls the whole
        # thing back if any operation fails.
        built = c.call("batch", operations=[
            {"op": "add_component", "type": "const", "x": 60, "y": 60,
             "properties": {"n": 3}},
            {"op": "add_component", "type": "func8", "x": 63, "y": 60,
             "properties": {"e": "x*2"}},
        ])
        ids = [r["result"]["added"]["id"] for r in built["results"]]
        c.call("connect", target=ids[1], input=1, source=ids[0])
        print("built : #%d -> #%d" % (ids[0], ids[1]))

        got = c.call("get_component", id=ids[1])
        print("check : inputs=%r e=%r" % (got["inputs"], got["properties"]["e"]))

        v = c.call("validate")
        print("valid : ok=%s errors=%d warnings=%d"
              % (v["ok"], len(v["errors"]), len(v["warnings"])))

        # Edits autosave; poll_changes reports edits made elsewhere.
        print("undo  : %d components"
              % c.call("undo")["summary"]["components"])
        print("events: %r" % c.call("poll_changes")["events"])
    finally:
        c.close()
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
