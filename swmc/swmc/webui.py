"""Interactive browser-based editor for Stormworks microprocessors.

Runs a small HTTP server over the same :class:`swmc.server.Session` the MCP
server uses, so a document edited in the browser and a document edited by an
agent are the *same* document -- no file round trip, no divergence.  Changes
from either side (and from the game writing the file) are pushed to connected
browsers over server-sent events.

    python -m swmc.webui --file "Complex Helicopter Gyro.xml"

Standard library only; SSE rather than websockets because it is one-way,
reconnects by itself, and needs no handshake code.
"""

from __future__ import annotations

import json
import mimetypes
import os
import queue
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from .model import EditError
from .nodetypes import BRIDGE_TYPES, COMPONENT_TYPES, DATA_TYPE
from .server import BATCH_OPS, Session, ToolError, Tools

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

#: Visual footprint of a component, in the game's own grid units.  Measured
#: from real microprocessors: columns sit >= 1.25 apart, stacked rows >= 0.5.
BOX_W = 1.25
ROW_H = 0.25
MIN_H = 0.5
GRID = 0.25


def box_height(n_in, n_out):
    return max(MIN_H, ROW_H * max(n_in, n_out, 2))


# --------------------------------------------------------------------------- #
# document -> JSON for the canvas
# --------------------------------------------------------------------------- #

def type_catalogue():
    out = {"components": {}, "bridge": {}}
    for key, table in (("components", COMPONENT_TYPES), ("bridge", BRIDGE_TYPES)):
        for t in table.values():
            out[key][t.type_id] = {
                "type": t.type_id,
                "name": t.name,
                "cls": t.cls,
                "category": t.category,
                "description": t.description,
                "link_fields": t.link_fields,
                "variadic": t.variadic_inputs,
                "inputs": [{"field": f, "label": lbl, "dt": dt,
                            "dt_name": DATA_TYPE.get(dt, "?")}
                           for f, (lbl, dt) in zip(t.link_fields, t.inputs)],
                "outputs": [{"index": i, "label": lbl, "dt": dt,
                             "dt_name": DATA_TYPE.get(dt, "?")}
                            for i, (lbl, dt) in enumerate(t.outputs)],
                "properties": [{"field": f, "kind": k}
                               for f, k in t.design_fields if k != "link"],
            }
    return out


def doc_json(state, path):
    doc = state.doc
    comps = []
    for c in doc.all_components():
        spec = c.spec
        fields = spec.link_fields
        n_in = len(fields)
        n_out = max(1, len(spec.outputs))
        wired = c.links()
        comps.append({
            "id": c.id,
            "type": c.type_id,
            "bridge": c.bridge,
            "name": spec.name,
            "label": c.name,
            "category": spec.category,
            "x": c.pos[0],
            "y": c.pos[1],
            "w": BOX_W,
            "h": box_height(n_in, n_out),
            "in_fields": fields,
            "n_out": n_out,
            "properties": c.properties(),
            "inputs": {k: v for k, v in wired.items() if v},
        })
    wires = []
    for c in comps:
        for field, link in c["inputs"].items():
            wires.append({
                "to": c["id"], "field": field,
                "index": c["in_fields"].index(field) if field in c["in_fields"] else 0,
                "from": link["component_id"], "out": link["id"],
            })
    issues = doc.validate()
    return {
        "path": path,
        "version": state.version,
        "dirty": state.dirty,
        "conflict": state.conflict,
        "header": {"name": doc.name, "description": doc.description,
                   "width": doc.size[0], "length": doc.size[1]},
        "components": comps,
        "wires": wires,
        "io_pins": doc.io_pins,
        "issues": issues,
        "undo_depth": len(state.undo),
        "redo_depth": len(state.redo),
        "grid": GRID,
    }


# --------------------------------------------------------------------------- #
# server
# --------------------------------------------------------------------------- #

class Hub:
    """Fans session changes out to every connected browser."""

    def __init__(self, session: Session):
        self.session = session
        self.tools = Tools(session)
        self.clients = []
        self.lock = threading.Lock()
        session.add_listener(self._on_change)

    def _on_change(self, path, reason):
        msg = json.dumps({"path": path, "reason": reason, "at": time.time()})
        with self.lock:
            targets = list(self.clients)
        for q in targets:
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass

    def subscribe(self):
        q = queue.Queue(maxsize=64)
        with self.lock:
            self.clients.append(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            if q in self.clients:
                self.clients.remove(q)


class Handler(BaseHTTPRequestHandler):
    server_version = "swmc-webui"
    hub: Hub = None          # injected on the server instance

    # -- helpers ------------------------------------------------------------
    def log_message(self, fmt, *args):
        pass  # the default logger writes to stderr on every request

    def _send(self, code, body, ctype="application/json; charset=utf-8",
              extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def _json(self, payload, code=200):
        self._send(code, json.dumps(payload, default=str))

    def _error(self, message, code=400):
        self._json({"error": str(message)}, code)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _state(self, query):
        path = (query.get("path") or [None])[0]
        return self.hub.session.resolve(path)

    # -- routes -------------------------------------------------------------
    def do_GET(self):
        url = urlparse(self.path)
        route = url.path
        query = parse_qs(url.query)
        try:
            if route in ("/", "/index.html"):
                return self._static("index.html")
            if route.startswith("/static/"):
                return self._static(route[len("/static/"):])
            if route == "/api/types":
                return self._json(type_catalogue())
            if route == "/api/state":
                path, state = self._state(query)
                return self._json(doc_json(state, path))
            if route == "/api/open":
                target = unquote((query.get("path") or [""])[0])
                self.hub.session.open(target)
                path, state = self.hub.session.resolve(target)
                return self._json(doc_json(state, path))
            if route == "/api/documents":
                with self.hub.session.lock:
                    return self._json({"open": [
                        {"path": p, "name": st.doc.name, "version": st.version,
                         "dirty": st.dirty, "conflict": st.conflict}
                        for p, st in sorted(self.hub.session.docs.items())]})
            if route == "/api/events":
                return self._events()
            return self._error("no route %s" % route, 404)
        except (ToolError, EditError) as exc:
            return self._error(exc, 400)
        except Exception as exc:
            traceback.print_exc()
            return self._error("%s: %s" % (type(exc).__name__, exc), 500)

    def do_POST(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        try:
            body = self._body()
            if url.path == "/api/edit":
                return self._edit(body, query)
            if url.path == "/api/call":
                name = body.get("tool")
                if name not in ALLOWED_TOOLS:
                    return self._error("tool %r is not exposed to the ui" % name)
                fn = getattr(self.hub.tools, name)
                result = fn(**(body.get("args") or {}))
                path, state = self._state(query)
                return self._json({"result": result, "state": doc_json(state, path)})
            return self._error("no route %s" % url.path, 404)
        except (ToolError, EditError) as exc:
            return self._error(exc, 400)
        except TypeError as exc:
            return self._error("bad arguments: %s" % exc, 400)
        except Exception as exc:
            traceback.print_exc()
            return self._error("%s: %s" % (type(exc).__name__, exc), 500)

    def _edit(self, body, query):
        ops = body.get("ops") or []
        for op in ops:
            if op.get("op") not in BATCH_OPS:
                return self._error("operation %r not allowed" % op.get("op"))
        path = (query.get("path") or [None])[0]
        if ops:
            self.hub.tools.batch(operations=ops, path=path)
        p, state = self.hub.session.resolve(path)
        return self._json(doc_json(state, p))

    def _static(self, name):
        name = name.lstrip("/").replace("..", "")
        full = os.path.join(STATIC, name)
        if not os.path.isfile(full):
            return self._error("not found: %s" % name, 404)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        with open(full, "rb") as fh:
            self._send(200, fh.read(), ctype)

    def _events(self):
        q = self.hub.subscribe()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    msg = q.get(timeout=15)
                    payload = "event: changed\ndata: %s\n\n" % msg
                except queue.Empty:
                    payload = ": ping\n\n"       # keeps proxies from timing out
                self.wfile.write(payload.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
            pass
        finally:
            self.hub.unsubscribe(q)


#: Tools the browser may invoke directly. Deliberately excludes anything that
#: writes to an arbitrary path.
ALLOWED_TOOLS = {"undo", "redo", "save", "reload", "validate", "summary",
                 "set_autosave", "describe_type", "list_types", "get_component",
                 "trace", "raw_xml", "io_pins", "add_io_pin"}


class WebUI:
    """Owns the HTTP server thread."""

    def __init__(self, session, host="127.0.0.1", port=8765):
        self.session = session
        self.hub = Hub(session)
        self.host = host
        self.port = port
        self.httpd = None
        self.thread = None

    @property
    def url(self):
        return "http://%s:%d/" % (self.host, self.port)

    def start(self):
        if self.httpd:
            return self.url
        handler = type("BoundHandler", (Handler,), {"hub": self.hub})
        last = None
        for port in range(self.port, self.port + 20):
            try:
                self.httpd = ThreadingHTTPServer((self.host, port), handler)
                self.port = port
                break
            except OSError as exc:
                last = exc
        if not self.httpd:
            raise RuntimeError("no free port in %d..%d (%s)"
                               % (self.port, self.port + 19, last))
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       name="swmc-webui", daemon=True)
        self.thread.start()
        return self.url

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        self.thread = None


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog="swmc-webui",
        description="Interactive editor for Stormworks microprocessor XML files.")
    ap.add_argument("--file", action="append", default=[],
                    help="Open this .xml at startup (repeatable).")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-autosave", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--poll-interval", type=float, default=0.4)
    args = ap.parse_args(argv)

    session = Session(autosave=not args.no_autosave, poll_interval=args.poll_interval)
    for f in args.file:
        session.open(f)
        print("opened %s" % os.path.abspath(f))

    ui = WebUI(session, args.host, args.port)
    url = ui.start()
    print("editor at %s" % url)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nstopping")
        ui.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
