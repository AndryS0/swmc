"""MCP server exposing the Stormworks microprocessor editor over stdio.

Implemented directly against the JSON-RPC wire protocol rather than the ``mcp``
SDK so the server runs on a bare CPython with nothing installed.

Transport: newline-delimited JSON on stdin/stdout.  stdout carries protocol
traffic only -- all diagnostics go to stderr.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback

from .model import EditError, Microprocessor
from .nodetypes import BRIDGE_TYPES, COMPONENT_TYPES, DATA_TYPE, find_type
from .watch import FileWatcher

SERVER_NAME = "stormworks-microprocessor"
SERVER_VERSION = "1.0.0"
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_PROTOCOL = "2024-11-05"

MAX_UNDO = 50


def log(*parts):
    print("[swmc]", *parts, file=sys.stderr, flush=True)


class ToolError(Exception):
    """A tool failed in a way the model should see and can act on."""


# --------------------------------------------------------------------------- #
# document sessions
# --------------------------------------------------------------------------- #

class DocState:
    def __init__(self, doc: Microprocessor):
        self.doc = doc
        self.dirty = False
        self.undo = []
        self.redo = []
        self.conflict = False
        self.last_external = None
        #: Monotonic counter bumped on every change from any source. Clients
        #: (the web UI, other editors) compare it to know when to refetch.
        self.version = 0

    def snapshot(self):
        self.undo.append(self.doc.to_string())
        if len(self.undo) > MAX_UNDO:
            self.undo.pop(0)
        self.redo.clear()


class Session:
    """Owns every open document plus the watcher that keeps them fresh."""

    def __init__(self, autosave=True, poll_interval=0.4):
        self.docs = {}
        self.autosave = autosave
        self.events = []
        self.lock = threading.RLock()
        self.watcher = FileWatcher(poll_interval, on_change=self._on_change)
        #: Callables invoked as ``listener(path, reason)`` after any change.
        #: The MCP server uses one to emit resource notifications; the web UI
        #: uses one to push server-sent events.
        self.listeners = []
        #: Set when the browser editor is running on this session.
        self.webui = None

    def add_listener(self, fn):
        self.listeners.append(fn)
        return fn

    def fire(self, path, reason):
        for fn in list(self.listeners):
            try:
                fn(path, reason)
            except Exception:
                log("listener failed\n", traceback.format_exc())

    # -- watching -----------------------------------------------------------
    def _on_change(self, events):
        with self.lock:
            for ev in events:
                path = ev["path"]
                state = self.docs.get(path)
                if state is None:
                    self.events.append(ev)
                    continue
                if state.dirty:
                    state.conflict = True
                    ev = dict(ev, note="file changed on disk while you have unsaved "
                                        "edits; use reload(force=true) to discard "
                                        "them or save(force=true) to overwrite")
                else:
                    try:
                        fresh = Microprocessor.load(path)
                        state.doc = fresh
                        state.undo.clear()
                        state.redo.clear()
                        ev = dict(ev, note="reloaded automatically",
                                  components=len(fresh.components))
                    except Exception as exc:
                        ev = dict(ev, note="reload failed: %s" % exc)
                state.last_external = ev
                state.version += 1
                self.events.append(ev)
            if len(self.events) > 200:
                del self.events[:-200]
        for ev in events:
            self.fire(ev["path"], "external")

    def drain_events(self):
        self.watcher.poll_once()
        with self.lock:
            out, self.events = self.events, []
            return out

    def pending_note(self, path):
        """Non-destructive peek used to annotate every tool result."""
        self.watcher.poll_once()
        with self.lock:
            state = self.docs.get(os.path.abspath(path))
            if state and state.conflict:
                return ("WARNING: %s changed on disk and you have unsaved edits. "
                        "reload(force=true) discards yours; save(force=true) "
                        "overwrites theirs." % path)
        return None

    # -- documents ----------------------------------------------------------
    def open(self, path):
        path = os.path.abspath(path)
        if not os.path.exists(path):
            raise ToolError("no such file: %s" % path)
        doc = Microprocessor.load(path)
        with self.lock:
            self.docs[path] = DocState(doc)
        self.watcher.watch(path)
        return path

    def close(self, path):
        path = os.path.abspath(path)
        with self.lock:
            state = self.docs.pop(path, None)
        self.watcher.unwatch(path)
        return state is not None

    def resolve(self, path=None):
        """Return ``(path, DocState)``; defaults to the only open document."""
        with self.lock:
            if path:
                p = os.path.abspath(path)
                if p not in self.docs:
                    self.open(p)
                return p, self.docs[p]
            if not self.docs:
                raise ToolError("no document is open; call open(path=...) first")
            if len(self.docs) > 1:
                raise ToolError("%d documents are open, pass path=: %s"
                                % (len(self.docs), ", ".join(sorted(self.docs))))
            p = next(iter(self.docs))
            return p, self.docs[p]

    def after_edit(self, path, state, force=False):
        """Snapshot bookkeeping plus autosave."""
        state.dirty = True
        state.version += 1
        try:
            if self.autosave and not state.conflict:
                return self.save(path, state, force=force)
            return None
        finally:
            self.fire(path, "edit")

    def save(self, path, state, force=False, backup=False):
        if state.conflict and not force:
            raise ToolError(
                "%s was modified on disk after you loaded it. Re-check it, then "
                "call save(force=true) to overwrite, or reload(force=true) to "
                "throw away your edits." % path)
        state.doc.save(path, backup=backup)
        self.watcher.mark_self_write(path)
        state.dirty = False
        state.conflict = False
        return path


# --------------------------------------------------------------------------- #
# tool implementations
# --------------------------------------------------------------------------- #

def _comp_brief(c):
    d = {"id": c.id, "type": c.type_id, "type_name": c.spec.name,
         "x": c.pos[0], "y": c.pos[1]}
    if c.bridge:
        d["bridge"] = True
    if c.name:
        d["label"] = c.name
    return d


class Tools:
    def __init__(self, session: Session):
        self.s = session

    # -- catalogue (no document needed) -------------------------------------
    def list_types(self, query=None, category=None, bridge=False):
        table = BRIDGE_TYPES if bridge else COMPONENT_TYPES
        rows = []
        for t in table.values():
            if category and t.category != category:
                continue
            if query:
                q = query.lower()
                if q not in t.name.lower() and q not in t.cls.lower() \
                        and q not in (t.description or "").lower():
                    continue
            rows.append({"type": t.type_id, "name": t.name, "category": t.category,
                         "inputs": len(t.inputs), "outputs": len(t.outputs)})
        return {"count": len(rows), "types": rows}

    def describe_type(self, type):
        t = find_type(type)
        return {
            "type": t.type_id,
            "name": t.name,
            "class": t.cls,
            "category": t.category,
            "mesh": t.mesh,
            "description": t.description,
            "inputs": [{"index": i + 1, "name": n, "label": lbl,
                        "data_type": DATA_TYPE.get(dt, dt)}
                       for i, ((lbl, dt), n) in enumerate(zip(t.inputs, t.link_fields))],
            "outputs": [{"index": i, "label": lbl, "data_type": DATA_TYPE.get(dt, dt)}
                        for i, (lbl, dt) in enumerate(t.outputs)],
            "properties": [{"field": f, "kind": k} for f, k in t.design_fields
                           if k != "link"],
            "link_fields": t.link_fields,
        }

    # -- document lifecycle -------------------------------------------------
    def open(self, path):
        p = self.s.open(path)
        _, state = self.s.resolve(p)
        return {"opened": p, "summary": state.doc.summary(),
                "autosave": self.s.autosave}

    def close(self, path=None):
        p, _ = self.s.resolve(path)
        return {"closed": p, "was_open": self.s.close(p)}

    def list_open(self):
        with self.s.lock:
            return {"open": [
                {"path": p, "name": st.doc.name, "components": len(st.doc.components),
                 "unsaved_changes": st.dirty, "conflict": st.conflict}
                for p, st in sorted(self.s.docs.items())]}

    def summary(self, path=None):
        _, state = self.s.resolve(path)
        return state.doc.summary()

    def save(self, path=None, save_as=None, force=False, backup=False):
        p, state = self.s.resolve(path)
        if save_as:
            state.doc.save(save_as, backup=backup)
            return {"saved": os.path.abspath(save_as), "copy": True}
        self.s.save(p, state, force=force, backup=backup)
        return {"saved": p, "unsaved_changes": state.dirty}

    def reload(self, path=None, force=False):
        p, state = self.s.resolve(path)
        if state.dirty and not force:
            raise ToolError("you have unsaved edits; pass force=true to discard them")
        state.doc = Microprocessor.load(p)
        state.dirty = False
        state.conflict = False
        state.undo.clear()
        state.redo.clear()
        state.version += 1
        self.s.watcher.mark_self_write(p)
        self.s.fire(p, "reload")
        return {"reloaded": p, "summary": state.doc.summary()}

    def poll_changes(self, path=None):
        events = self.s.drain_events()
        if path:
            p = os.path.abspath(path)
            events = [e for e in events if e["path"] == p]
        return {"count": len(events), "events": events,
                "watching": self.s.watcher.watched()}

    def set_autosave(self, enabled):
        self.s.autosave = bool(enabled)
        return {"autosave": self.s.autosave}

    # -- graphical editor ---------------------------------------------------
    def gui_open(self, port=8765, host="127.0.0.1", browser=True):
        """Start the browser editor on *this* session, so both edit one document."""
        # Imported lazily: webui imports from this module.
        from .webui import WebUI
        if self.s.webui is None:
            self.s.webui = WebUI(self.s, host, port)
            url = self.s.webui.start()
            log("web editor at", url)
        else:
            url = self.s.webui.url
        if browser:
            import webbrowser
            try:
                webbrowser.open(url)
            except Exception as exc:
                log("could not open a browser:", exc)
        return {"url": url, "opened_browser": bool(browser),
                "documents": sorted(self.s.docs),
                "note": "Edits made in the browser and through these tools act on "
                        "the same in-memory document."}

    def gui_status(self):
        ui = self.s.webui
        if ui is None or ui.httpd is None:
            return {"running": False}
        return {"running": True, "url": ui.url,
                "browsers_connected": len(ui.hub.clients)}

    def gui_close(self):
        ui = self.s.webui
        if ui is None or ui.httpd is None:
            return {"running": False}
        ui.stop()
        self.s.webui = None
        return {"running": False, "stopped": True}

    def undo(self, path=None):
        p, state = self.s.resolve(path)
        if not state.undo:
            if state.last_external:
                raise ToolError(
                    "nothing to undo: the undo history was dropped when %s was "
                    "reloaded after an external change (%s)"
                    % (p, state.last_external.get("note", "modified on disk")))
            raise ToolError("nothing to undo")
        state.redo.append(state.doc.to_string())
        text = state.undo.pop()
        state.doc = Microprocessor.loads(text, p)
        self.s.after_edit(p, state, force=True)
        return {"undone": True, "remaining": len(state.undo),
                "summary": state.doc.summary()}

    def redo(self, path=None):
        p, state = self.s.resolve(path)
        if not state.redo:
            raise ToolError("nothing to redo")
        state.undo.append(state.doc.to_string())
        text = state.redo.pop()
        state.doc = Microprocessor.loads(text, p)
        self.s.after_edit(p, state, force=True)
        return {"redone": True, "summary": state.doc.summary()}

    # -- reading ------------------------------------------------------------
    def list_components(self, path=None, type=None, label=None, category=None,
                        region=None, limit=200, offset=0, detail=False):
        _, state = self.s.resolve(path)
        comps = state.doc.find(type=type, label=label, category=category,
                               region=tuple(region) if region else None)
        total = len(comps)
        page = comps[offset:offset + limit]
        rows = [c.to_dict() if detail else _comp_brief(c) for c in page]
        return {"total": total, "offset": offset, "returned": len(rows),
                "components": rows}

    def get_component(self, id, path=None):
        _, state = self.s.resolve(path)
        c = state.doc.get(id)
        d = c.to_dict()
        d["spec"] = self.describe_type(c.type_id) if not c.bridge else {
            "type": c.type_id, "name": c.spec.name, "class": c.spec.cls,
            "link_fields": c.spec.link_fields}
        fed_by_this = [o.id for o in state.doc.all_components()
                       for lk in o.links().values()
                       if lk and lk["component_id"] == c.id]
        d["feeds"] = sorted(set(fed_by_this))
        return d

    def io_pins(self, path=None):
        _, state = self.s.resolve(path)
        return {"pins": state.doc.io_pins}

    def validate(self, path=None):
        _, state = self.s.resolve(path)
        issues = state.doc.validate()
        return {"ok": not any(i["level"] == "error" for i in issues),
                "errors": [i for i in issues if i["level"] == "error"],
                "warnings": [i for i in issues if i["level"] == "warning"]}

    def trace(self, id, direction="upstream", depth=3, path=None):
        _, state = self.s.resolve(path)
        doc = state.doc
        doc.get(id)
        downstream = doc.graph()
        upstream = {}
        for comp in doc.all_components():
            upstream[comp.id] = sorted({lk["component_id"]
                                        for lk in comp.links().values() if lk})
        table = upstream if direction == "upstream" else downstream
        seen, frontier, levels = {int(id)}, [int(id)], []
        for _ in range(max(1, int(depth))):
            nxt = []
            for cid in frontier:
                for other in table.get(cid, []):
                    if other not in seen:
                        seen.add(other)
                        nxt.append(other)
            if not nxt:
                break
            levels.append([_comp_brief(doc.get(c)) for c in nxt])
            frontier = nxt
        return {"root": int(id), "direction": direction, "levels": levels}

    def raw_xml(self, id=None, path=None):
        """Escape hatch: the literal XML of one component, or the whole file."""
        from . import sxml
        p, state = self.s.resolve(path)
        if id is None:
            return {"path": p, "xml": state.doc.to_string()}
        c = state.doc.get(id)
        return {"id": c.id, "xml": sxml.tostring(c.c, decl="", indent="  ")}

    # -- writing ------------------------------------------------------------
    def add_component(self, type, x=0.0, y=0.0, properties=None, inputs=None,
                      path=None, bridge=False, auto_place=False):
        p, state = self.s.resolve(path)
        state.snapshot()
        if auto_place:
            x, y = state.doc.free_position((x, y))
        c = state.doc.add(type, x, y, properties=properties, inputs=inputs,
                          bridge=bridge)
        self.s.after_edit(p, state)
        return {"added": c.to_dict()}

    def remove_component(self, id, rewire=False, path=None):
        p, state = self.s.resolve(path)
        state.snapshot()
        info = state.doc.remove(id, rewire=rewire)
        self.s.after_edit(p, state)
        return info

    def move_component(self, id, x=None, y=None, dx=0.0, dy=0.0, path=None):
        p, state = self.s.resolve(path)
        state.snapshot()
        if isinstance(id, list):
            if x is not None or y is not None:
                raise ToolError("moving several components accepts dx/dy only")
            moved = state.doc.move_many(id, dx=dx, dy=dy)
            self.s.after_edit(p, state)
            return {"moved": [_comp_brief(c) for c in moved]}
        c = state.doc.move(id, x=x, y=y, dx=dx, dy=dy)
        self.s.after_edit(p, state)
        return {"moved": _comp_brief(c)}

    def connect(self, target, input, source, source_output=0, path=None):
        p, state = self.s.resolve(path)
        state.snapshot()
        name = state.doc.connect(target, input, source, source_output)
        self.s.after_edit(p, state)
        return {"target": int(target), "input": name, "source": int(source),
                "source_output": int(source_output)}

    def disconnect(self, target, input, path=None):
        p, state = self.s.resolve(path)
        state.snapshot()
        ok = state.doc.disconnect(target, input)
        self.s.after_edit(p, state)
        return {"target": int(target), "input": input, "was_connected": ok}

    def set_property(self, id, field=None, value=None, properties=None, path=None):
        p, state = self.s.resolve(path)
        state.snapshot()
        c = state.doc.get(id)
        if field is not None:
            c.set_property(field, value)
        for k, v in (properties or {}).items():
            c.set_property(k, v)
        state.doc.revision += 1
        self.s.after_edit(p, state)
        return {"id": c.id, "properties": c.properties()}

    def set_header(self, name=None, description=None, path=None):
        p, state = self.s.resolve(path)
        state.snapshot()
        if name is not None:
            state.doc.name = name
        if description is not None:
            state.doc.description = description
        self.s.after_edit(p, state)
        return {"name": state.doc.name, "description": state.doc.description}

    def add_io_pin(self, component_id, label, x=0, z=0, mode=None, type=None,
                   description=None, path=None):
        p, state = self.s.resolve(path)
        state.snapshot()
        pin = state.doc.add_io_pin(component_id, label, x=x, z=z, mode=mode,
                                   type=type, description=description)
        self.s.after_edit(p, state)
        return {"pin_id": pin, "pins": state.doc.io_pins}

    def batch(self, operations, path=None, stop_on_error=True):
        """Apply several edits under one undo step.

        Building a circuit is many small edits; doing them in one call keeps
        the file consistent on disk and makes a single undo restore the lot.
        """
        p, state = self.s.resolve(path)
        state.snapshot()
        before = state.doc.to_string()
        results = []
        saved_autosave, self.s.autosave = self.s.autosave, False
        try:
            for i, op in enumerate(operations):
                if not isinstance(op, dict) or "op" not in op:
                    raise ToolError("operation %d needs an 'op' key" % i)
                name = op["op"]
                if name not in BATCH_OPS:
                    raise ToolError("operation %d: %r is not batchable (allowed: %s)"
                                    % (i, name, ", ".join(sorted(BATCH_OPS))))
                args = {k: v for k, v in op.items() if k != "op"}
                args["path"] = p
                try:
                    results.append({"op": name, "ok": True,
                                    "result": getattr(self, name)(**args)})
                except Exception as exc:
                    results.append({"op": name, "ok": False, "error": str(exc)})
                    if stop_on_error:
                        state.doc = Microprocessor.loads(before, p)
                        if state.undo:
                            state.undo.pop()
                        raise ToolError(
                            "operation %d (%s) failed: %s -- nothing was applied"
                            % (i, name, exc))
        finally:
            self.s.autosave = saved_autosave
        self.s.after_edit(p, state)
        return {"applied": len(results), "results": results}


BATCH_OPS = {"add_component", "remove_component", "move_component", "connect",
             "disconnect", "set_property", "set_header", "add_io_pin"}


# --------------------------------------------------------------------------- #
# tool schemas
# --------------------------------------------------------------------------- #

def _s(**props):
    return {"type": "object", "properties": props}


PATH_ARG = {"type": "string",
            "description": "Microprocessor .xml to act on. Optional when exactly "
                           "one document is open."}
ID_ARG = {"type": "integer", "description": "Component id (the <object id=...> value)."}

TOOLS = [
    {
        "name": "open",
        "description": "Open a Stormworks microprocessor .xml, start watching it for "
                       "external changes, and return a summary. Call this first.",
        "inputSchema": {"type": "object", "required": ["path"],
                        "properties": {"path": {"type": "string",
                                                "description": "Path to the .xml file."}}},
    },
    {
        "name": "close",
        "description": "Stop tracking a document and stop watching its file.",
        "inputSchema": _s(path=PATH_ARG),
    },
    {
        "name": "list_open",
        "description": "List the open documents with their unsaved/conflict state.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "summary",
        "description": "Name, size, component counts, bounding box and a "
                       "per-component-type histogram.",
        "inputSchema": _s(path=PATH_ARG),
    },
    {
        "name": "list_types",
        "description": "Browse the 60 microprocessor component types (and the 10 "
                       "bridge pin types). Use this to find the type id or alias to "
                       "pass to add_component.",
        "inputSchema": _s(
            query={"type": "string", "description": "Substring filter on name/class/description."},
            category={"type": "string", "enum": ["arithmetic", "logical", "control",
                                                 "composite", "property"]},
            bridge={"type": "boolean", "description": "List <components_bridge> types instead."}),
    },
    {
        "name": "describe_type",
        "description": "Full detail for one component type: inputs with their data "
                       "types, outputs, and every editable property field.",
        "inputSchema": {"type": "object", "required": ["type"],
                        "properties": {"type": {"type": ["integer", "string"],
                                                "description": "Type id, alias (e.g. 'func8') "
                                                               "or display name."}}},
    },
    {
        "name": "list_components",
        "description": "List components, optionally filtered by type, label, category "
                       "or a rectangular region.",
        "inputSchema": _s(
            path=PATH_ARG,
            type={"type": ["integer", "string"], "description": "Type id, alias or name."},
            label={"type": "string", "description": "Case-insensitive substring of the label."},
            category={"type": "string"},
            region={"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4,
                    "description": "[x0, y0, x1, y1] bounding box."},
            detail={"type": "boolean", "description": "Include properties and wiring."},
            limit={"type": "integer", "default": 200},
            offset={"type": "integer", "default": 0}),
    },
    {
        "name": "get_component",
        "description": "Everything about one component: position, properties, what it "
                       "reads from, what reads it, and its type specification.",
        "inputSchema": {"type": "object", "required": ["id"],
                        "properties": {"id": ID_ARG, "path": PATH_ARG}},
    },
    {
        "name": "io_pins",
        "description": "List the microprocessor's external pins (the <nodes> section) "
                       "and the bridge component each one is bound to.",
        "inputSchema": _s(path=PATH_ARG),
    },
    {
        "name": "trace",
        "description": "Walk the signal graph up or down from a component, level by level.",
        "inputSchema": {"type": "object", "required": ["id"], "properties": {
            "id": ID_ARG,
            "direction": {"type": "string", "enum": ["upstream", "downstream"],
                          "default": "upstream"},
            "depth": {"type": "integer", "default": 3},
            "path": PATH_ARG}},
    },
    {
        "name": "validate",
        "description": "Check the document: dangling links, duplicate ids, orphaned io "
                       "pins (errors) and data-type mismatches on wires (warnings).",
        "inputSchema": _s(path=PATH_ARG),
    },
    {
        "name": "raw_xml",
        "description": "The literal XML of one component, or of the whole document when "
                       "no id is given. Use for anything this API does not model.",
        "inputSchema": _s(id=ID_ARG, path=PATH_ARG),
    },
    {
        "name": "add_component",
        "description": "Add a component. 'type' takes an id, an alias ('func8', 'and', "
                       "'pid') or a display name. Properties and input wiring can be "
                       "supplied inline.",
        "inputSchema": {"type": "object", "required": ["type"], "properties": {
            "type": {"type": ["integer", "string"]},
            "x": {"type": "number", "default": 0},
            "y": {"type": "number", "default": 0},
            "auto_place": {"type": "boolean",
                           "description": "Nudge to the nearest free grid slot around (x, y)."},
            "properties": {"type": "object",
                           "description": "Field -> value, e.g. {\"e\": \"x+y\"} or "
                                          "{\"min\": -1, \"max\": 1}."},
            "inputs": {"type": "object",
                       "description": "Input -> source component id, e.g. {\"in1\": 42}."},
            "bridge": {"type": "boolean", "description": "Create a <components_bridge> pin."},
            "path": PATH_ARG}},
    },
    {
        "name": "remove_component",
        "description": "Delete a component. Inbound wires are cleared; with rewire=true "
                       "they are reconnected to this component's own first input, which "
                       "splices a pass-through node out of a chain.",
        "inputSchema": {"type": "object", "required": ["id"], "properties": {
            "id": ID_ARG,
            "rewire": {"type": "boolean", "default": False},
            "path": PATH_ARG}},
    },
    {
        "name": "move_component",
        "description": "Move one component (absolute x/y or relative dx/dy) or a list of "
                       "component ids (dx/dy only).",
        "inputSchema": {"type": "object", "required": ["id"], "properties": {
            "id": {"type": ["integer", "array"], "items": {"type": "integer"}},
            "x": {"type": "number"}, "y": {"type": "number"},
            "dx": {"type": "number", "default": 0}, "dy": {"type": "number", "default": 0},
            "path": PATH_ARG}},
    },
    {
        "name": "connect",
        "description": "Wire a source component's output into a target component's input. "
                       "'input' accepts 'in2', the index 2, or the input's label.",
        "inputSchema": {"type": "object", "required": ["target", "input", "source"],
                        "properties": {
                            "target": {"type": "integer"},
                            "input": {"type": ["string", "integer"]},
                            "source": {"type": "integer"},
                            "source_output": {"type": "integer", "default": 0,
                                              "description": "Output index on the source; "
                                                             "0 is the first output."},
                            "path": PATH_ARG}},
    },
    {
        "name": "disconnect",
        "description": "Remove the wire feeding one input of a component.",
        "inputSchema": {"type": "object", "required": ["target", "input"], "properties": {
            "target": {"type": "integer"},
            "input": {"type": ["string", "integer"]},
            "path": PATH_ARG}},
    },
    {
        "name": "set_property",
        "description": "Set one property (field/value) or several at once (properties). "
                       "Number properties accept a plain number or {text, value} to keep "
                       "the expression the user typed.",
        "inputSchema": {"type": "object", "required": ["id"], "properties": {
            "id": ID_ARG,
            "field": {"type": "string"},
            "value": {},
            "properties": {"type": "object"},
            "path": PATH_ARG}},
    },
    {
        "name": "set_header",
        "description": "Rename the microprocessor or change its description.",
        "inputSchema": _s(name={"type": "string"}, description={"type": "string"},
                          path=PATH_ARG),
    },
    {
        "name": "add_io_pin",
        "description": "Expose a bridge component as a pin on the microprocessor's face.",
        "inputSchema": {"type": "object", "required": ["component_id", "label"],
                        "properties": {
                            "component_id": {"type": "integer",
                                             "description": "Id of a <components_bridge> entry."},
                            "label": {"type": "string"},
                            "x": {"type": "integer", "default": 0},
                            "z": {"type": "integer", "default": 0},
                            "mode": {"type": "integer"},
                            "type": {"type": "integer"},
                            "description": {"type": "string"},
                            "path": PATH_ARG}},
    },
    {
        "name": "batch",
        "description": "Apply many edits atomically under a single undo step. Prefer this "
                       "when building a circuit: on failure nothing is applied.",
        "inputSchema": {"type": "object", "required": ["operations"], "properties": {
            "operations": {"type": "array", "items": {"type": "object"},
                           "description": "Each item is {\"op\": \"add_component\", ...rest "
                                          "of that tool's arguments}. Allowed ops: "
                                          + ", ".join(sorted(BATCH_OPS))},
            "stop_on_error": {"type": "boolean", "default": True},
            "path": PATH_ARG}},
    },
    {
        "name": "save",
        "description": "Write the document to disk. Only needed when autosave is off, or "
                       "to save a copy elsewhere.",
        "inputSchema": _s(path=PATH_ARG,
                          save_as={"type": "string", "description": "Write a copy here instead."},
                          force={"type": "boolean",
                                 "description": "Overwrite even if the file changed on disk."},
                          backup={"type": "boolean", "description": "Keep a .bak of the old file."}),
    },
    {
        "name": "reload",
        "description": "Re-read the file from disk, discarding in-memory edits with force=true.",
        "inputSchema": _s(path=PATH_ARG, force={"type": "boolean"}),
    },
    {
        "name": "poll_changes",
        "description": "Return external file-change events seen since the last poll. Clean "
                       "documents are reloaded automatically; dirty ones are flagged as "
                       "conflicts.",
        "inputSchema": _s(path=PATH_ARG),
    },
    {
        "name": "set_autosave",
        "description": "Autosave (on by default) writes the file after every edit so the "
                       "game sees changes immediately. Turn it off for large batches.",
        "inputSchema": {"type": "object", "required": ["enabled"],
                        "properties": {"enabled": {"type": "boolean"}}},
    },
    {
        "name": "gui_open",
        "description": "Launch the interactive graphical editor in the user's browser "
                       "and return its URL. It drives the same in-memory document as "
                       "these tools, so edits from either side appear on both "
                       "immediately. Use it whenever the user wants to see, arrange or "
                       "wire the circuit by hand.",
        "inputSchema": _s(
            port={"type": "integer", "default": 8765,
                  "description": "First port to try; the next free one is used."},
            host={"type": "string", "default": "127.0.0.1"},
            browser={"type": "boolean", "default": True,
                     "description": "Also open the default browser."}),
    },
    {
        "name": "gui_status",
        "description": "Whether the graphical editor is running, its URL, and how many "
                       "browser tabs are connected.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "gui_close",
        "description": "Shut the graphical editor's web server down.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "undo",
        "description": "Undo the last edit.",
        "inputSchema": _s(path=PATH_ARG),
    },
    {
        "name": "redo",
        "description": "Redo the last undone edit.",
        "inputSchema": _s(path=PATH_ARG),
    },
]


# --------------------------------------------------------------------------- #
# JSON-RPC plumbing
# --------------------------------------------------------------------------- #

class Server:
    def __init__(self, session: Session):
        self.session = session
        self.tools = Tools(session)
        self.protocol = DEFAULT_PROTOCOL
        self.subscribed = set()
        self._out_lock = threading.Lock()
        session.add_listener(lambda path, reason: self._resource_updated(path))

    # -- transport ----------------------------------------------------------
    def _send(self, message):
        data = json.dumps(message, ensure_ascii=False, default=str)
        with self._out_lock:
            sys.stdout.write(data + "\n")
            sys.stdout.flush()

    def _resource_updated(self, path):
        uri = "file:///" + os.path.abspath(path).replace("\\", "/").lstrip("/")
        if uri in self.subscribed:
            self._send({"jsonrpc": "2.0", "method": "notifications/resources/updated",
                        "params": {"uri": uri}})

    # -- dispatch -----------------------------------------------------------
    def handle(self, msg):
        method = msg.get("method")
        mid = msg.get("id")
        params = msg.get("params") or {}

        if method is None:
            return None  # a response to something we sent; nothing to do
        try:
            if method == "initialize":
                want = params.get("protocolVersion")
                self.protocol = want if want in SUPPORTED_PROTOCOLS else DEFAULT_PROTOCOL
                result = {
                    "protocolVersion": self.protocol,
                    "capabilities": {"tools": {"listChanged": False},
                                     "resources": {"subscribe": True, "listChanged": True}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "instructions":
                        "Edit Stormworks microprocessor .xml files. open(path) first, "
                        "then list_types/describe_type to find component types and "
                        "add_component/connect/set_property to build. Edits autosave to "
                        "disk; poll_changes surfaces edits made in-game.",
                }
            elif method in ("notifications/initialized", "initialized",
                            "notifications/cancelled"):
                return None
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                result = self._call_tool(params)
            elif method == "resources/list":
                result = {"resources": self._resources()}
            elif method == "resources/read":
                result = self._read_resource(params.get("uri", ""))
            elif method == "resources/subscribe":
                self.subscribed.add(params.get("uri", ""))
                result = {}
            elif method == "resources/unsubscribe":
                self.subscribed.discard(params.get("uri", ""))
                result = {}
            elif method in ("prompts/list",):
                result = {"prompts": []}
            else:
                return {"jsonrpc": "2.0", "id": mid,
                        "error": {"code": -32601, "message": "unknown method %r" % method}}
        except ToolError as exc:
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32000, "message": str(exc)}}
        except Exception as exc:
            log("internal error in", method, "\n", traceback.format_exc())
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32603, "message": "%s: %s"
                                                         % (type(exc).__name__, exc)}}
        if mid is None:
            return None
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def _call_tool(self, params):
        name = params.get("name")
        args = params.get("arguments") or {}
        fn = getattr(self.tools, name, None)
        if fn is None or name.startswith("_") or not callable(fn):
            raise ToolError("unknown tool %r" % name)
        try:
            payload = fn(**args)
        except (ToolError, EditError) as exc:
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        except TypeError as exc:
            return {"content": [{"type": "text",
                                 "text": "bad arguments for %s: %s" % (name, exc)}],
                    "isError": True}
        except Exception as exc:
            log("tool", name, "failed\n", traceback.format_exc())
            return {"content": [{"type": "text",
                                 "text": "%s: %s" % (type(exc).__name__, exc)}],
                    "isError": True}

        note = None
        if isinstance(payload, dict):
            target = payload.get("path") or args.get("path")
            if target:
                note = self.session.pending_note(target)
            elif self.session.docs:
                try:
                    p, _ = self.session.resolve(None)
                    note = self.session.pending_note(p)
                except Exception:
                    note = None
        text = json.dumps(payload, indent=1, ensure_ascii=False, default=str)
        if note:
            text = note + "\n\n" + text
        return {"content": [{"type": "text", "text": text}],
                "structuredContent": payload if isinstance(payload, dict) else {"result": payload}}

    def _resources(self):
        out = []
        with self.session.lock:
            for p, st in sorted(self.session.docs.items()):
                out.append({
                    "uri": "file:///" + p.replace("\\", "/").lstrip("/"),
                    "name": st.doc.name or os.path.basename(p),
                    "description": "Stormworks microprocessor (%d components)"
                                   % len(st.doc.components),
                    "mimeType": "application/xml",
                })
        return out

    def _read_resource(self, uri):
        path = uri[len("file:///"):] if uri.startswith("file:///") else uri
        path = os.path.abspath(path.replace("/", os.sep))
        with self.session.lock:
            st = self.session.docs.get(path)
        if st is None:
            raise ToolError("not an open document: %s" % uri)
        return {"contents": [{"uri": uri, "mimeType": "application/xml",
                              "text": st.doc.to_string()}]}

    # -- main loop ----------------------------------------------------------
    def serve(self):
        log("ready on stdio; %d tools" % len(TOOLS))
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError as exc:
                self._send({"jsonrpc": "2.0", "id": None,
                            "error": {"code": -32700, "message": "parse error: %s" % exc}})
                continue
            if isinstance(msg, list):
                for item in msg:
                    resp = self.handle(item)
                    if resp:
                        self._send(resp)
                continue
            resp = self.handle(msg)
            if resp:
                self._send(resp)
        log("stdin closed, exiting")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog="swmc-server",
        description="MCP server for editing Stormworks microprocessor XML files.")
    ap.add_argument("--file", action="append", default=[],
                    help="Open this .xml at startup (repeatable).")
    ap.add_argument("--no-autosave", action="store_true",
                    help="Do not write the file after every edit.")
    ap.add_argument("--poll-interval", type=float, default=0.4,
                    help="Seconds between file-change checks (default 0.4).")
    args = ap.parse_args(argv)

    session = Session(autosave=not args.no_autosave, poll_interval=args.poll_interval)
    for f in args.file:
        try:
            session.open(f)
            log("opened", f)
        except Exception as exc:
            log("could not open %s: %s" % (f, exc))
    Server(session).serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
