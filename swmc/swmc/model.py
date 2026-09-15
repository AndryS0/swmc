"""Object model and editing operations for a Stormworks microprocessor file.

The document is kept as a live :mod:`swmc.sxml` tree so that anything this
library does not model explicitly -- dropdown ``<items>``, future component
fields, unknown attributes -- survives a load/save round trip untouched.
"""

from __future__ import annotations

import os
import re

from . import sxml
from .nodetypes import (
    BRIDGE_TYPES,
    COMPONENT_TYPES,
    DATA_TYPE,
    ComponentType,
    find_type,
)

__all__ = ["Microprocessor", "Component", "EditError", "fmt_num"]


class EditError(Exception):
    """An edit was rejected because it would produce an invalid document."""


def fmt_num(value):
    """Format a number the way the game does: no trailing ``.0``, no exponent."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    f = float(value)
    if f != f or f in (float("inf"), float("-inf")):
        raise EditError("not a finite number: %r" % (value,))
    if f == int(f) and abs(f) < 1e15:
        return str(int(f))
    s = repr(round(f, 6))
    if s.endswith(".0"):
        s = s[:-2]
    return s


def _num(text, default=0.0):
    if text is None or text == "":
        return default
    try:
        return float(text)
    except ValueError:
        return default


class Component:
    """One ``<c type="N"><object .../></c>`` entry.

    Wraps the underlying elements rather than copying them, so every mutation
    is reflected in the document immediately.
    """

    def __init__(self, doc, c_el, bridge=False):
        self.doc = doc
        self.c = c_el
        self.bridge = bridge
        obj = c_el.find("object")
        if obj is None:
            raise EditError("<c> without an <object> child")
        self.object = obj

    # -- identity -----------------------------------------------------------
    @property
    def type_id(self):
        return int(self.c.get("type", "0"))

    @property
    def spec(self) -> ComponentType:
        table = BRIDGE_TYPES if self.bridge else COMPONENT_TYPES
        return table[self.type_id]

    @property
    def id(self):
        return int(self.object.get("id", "0"))

    @id.setter
    def id(self, value):
        self.object.set("id", str(int(value)))

    @property
    def name(self):
        """Display label of this instance, if the type has one."""
        for key in ("name", "n", "l"):
            if self.spec.field_kind(key) == "attr_str" and key in self.object.attrib:
                return self.object.get(key)
        return None

    # -- position -----------------------------------------------------------
    @property
    def pos(self):
        p = self.object.find("pos")
        if p is None:
            return (0.0, 0.0)
        return (_num(p.get("x")), _num(p.get("y")))

    @pos.setter
    def pos(self, xy):
        x, y = xy
        p = self.object.find("pos")
        if p is None:
            p = sxml.Element("pos")
            self.object.insert(0, p)
        # The game omits a zero coordinate entirely.
        p.attrib.pop("x", None)
        p.attrib.pop("y", None)
        new = {}
        if float(x) != 0.0:
            new["x"] = fmt_num(x)
        if float(y) != 0.0:
            new["y"] = fmt_num(y)
        p.attrib = new

    # -- connections --------------------------------------------------------
    def link_names(self):
        """Input link element names this component type accepts, in order."""
        return self.spec.link_fields

    def links(self):
        """``{input_name: {"component_id": int, "id": int}}`` for wired inputs."""
        out = {}
        for name in self.link_names():
            el = self.object.find(name)
            if el is None:
                continue
            cid = el.get("component_id")
            if cid is None:
                out[name] = None  # element present but unwired
            else:
                out[name] = {"component_id": int(cid), "id": int(el.get("id", "0"))}
        return out

    def resolve_input(self, key):
        """Accept ``"in3"``, ``3`` or an input label and return the element name."""
        names = self.link_names()
        if isinstance(key, int):
            if not 1 <= key <= len(names):
                raise EditError(
                    "%s (type %d) has %d inputs, asked for #%d"
                    % (self.spec.name, self.type_id, len(names), key))
            return names[key - 1]
        s = str(key).strip()
        if s in names:
            return s
        if s.isdigit():
            return self.resolve_input(int(s))
        low = s.lower()
        for i, (label, _dt) in enumerate(self.spec.inputs):
            if label.lower() == low and i < len(names):
                return names[i]
        raise EditError(
            "%s (type %d) has no input %r; inputs are: %s"
            % (self.spec.name, self.type_id, key, ", ".join(names)))

    def connect(self, key, source_id, source_output=0):
        name = self.resolve_input(key)
        el = self.object.find(name)
        if el is None:
            el = sxml.Element(name)
            self._insert_link(name, el)
        el.attrib = {}
        if source_output:
            el.set("id", str(int(source_output)))
        el.set("component_id", str(int(source_id)))
        return name

    def disconnect(self, key):
        name = self.resolve_input(key)
        el = self.object.find(name)
        if el is None:
            return False
        self.object.remove(el)
        return True

    def _insert_link(self, name, el):
        """Insert a link element in serializer order (after <pos>)."""
        order = self.link_names()
        want = order.index(name)
        idx = len(self.object.children)
        for i, child in enumerate(self.object.children):
            if child.tag in order and order.index(child.tag) > want:
                idx = i
                break
            if child.tag not in order and child.tag != "pos":
                idx = i
                break
        self.object.insert(idx, el)

    # -- properties ---------------------------------------------------------
    def properties(self):
        """Every design-time field that is actually present, decoded."""
        out = {}
        for field, kind in self.spec.design_fields:
            if kind == "link" or field == "in%u":
                continue
            if kind in ("attr_str", "attr_int", "attr_float"):
                if field in self.object.attrib:
                    raw = self.object.get(field)
                    if kind == "attr_int":
                        out[field] = int(_num(raw))
                    elif kind == "attr_float":
                        out[field] = _num(raw)
                    else:
                        out[field] = raw
            elif kind == "prop_num":
                el = self.object.find(field)
                if el is not None:
                    out[field] = {"text": el.get("text", ""),
                                  "value": _num(el.get("value"))}
        return out

    def set_property(self, field, value):
        kind = self.spec.field_kind(field)
        if kind is None:
            known = [f for f, k in self.spec.design_fields if k != "link"]
            raise EditError(
                "%s (type %d) has no property %r; properties are: %s"
                % (self.spec.name, self.type_id, field,
                   ", ".join(known) if known else "(none)"))
        if kind == "link":
            raise EditError("%r is an input, use connect() instead" % field)
        if kind in ("state", "state_out"):
            raise EditError("%r is runtime state, not an editable property" % field)

        if kind == "attr_str":
            self.object.set(field, "" if value is None else str(value))
        elif kind == "attr_int":
            self.object.set(field, str(int(value)))
        elif kind == "attr_float":
            self.object.set(field, fmt_num(value))
        elif kind == "prop_num":
            el = self.object.find(field)
            if el is None:
                el = sxml.Element(field)
                self.object.append(el)
            if isinstance(value, dict):
                text = str(value.get("text", ""))
                num = value.get("value", _num(text))
            elif isinstance(value, str):
                text = value
                num = _num(value)
            else:
                text = fmt_num(value)
                num = float(value)
            el.attrib = {"text": text}
            if float(num) != 0.0:
                el.set("value", fmt_num(num))
        return self

    # -- misc ---------------------------------------------------------------
    def to_dict(self, with_links=True):
        d = {
            "id": self.id,
            "type": self.type_id,
            "type_name": self.spec.name,
            "category": self.spec.category,
            "pos": {"x": self.pos[0], "y": self.pos[1]},
        }
        if self.bridge:
            d["bridge"] = True
        if self.name:
            d["label"] = self.name
        props = self.properties()
        if props:
            d["properties"] = props
        if with_links:
            links = {k: v for k, v in self.links().items() if v}
            if links:
                d["inputs"] = {k: v["component_id"] if v["id"] == 0
                               else {"component_id": v["component_id"], "output": v["id"]}
                               for k, v in links.items()}
        return d

    def __repr__(self):
        return "<Component #%d %s at (%g, %g)>" % (
            self.id, self.spec.name, self.pos[0], self.pos[1])


class Microprocessor:
    """A loaded ``.xml`` microprocessor, with editing operations."""

    def __init__(self, root, decl, path=None):
        self.root = root
        self.decl = decl
        self.path = path
        if root.tag != "microprocessor":
            raise EditError("root element is <%s>, expected <microprocessor>" % root.tag)
        self.group = root.find("group")
        if self.group is None:
            raise EditError("missing <group> element")
        self._components_el = self.group.ensure("components")
        self._bridge_el = self.group.ensure("components_bridge")
        self._nodes_el = root.ensure("nodes")
        self.revision = 0

    # -- io -----------------------------------------------------------------
    @classmethod
    def load(cls, path):
        root, decl, _ = sxml.parse_file(path)
        return cls(root, decl, os.path.abspath(path))

    @classmethod
    def loads(cls, text, path=None):
        root, decl, _ = sxml.parse(text)
        return cls(root, decl, path)

    def to_string(self):
        return sxml.tostring(self.root, self.decl)

    def save(self, path=None, sync_states=True, backup=False):
        target = path or self.path
        if not target:
            raise EditError("no path to save to")
        if sync_states:
            self.sync_states()
        text = self.to_string()
        if backup and os.path.exists(target):
            bak = target + ".bak"
            with open(target, "r", encoding="utf-8", newline="") as fh:
                old = fh.read()
            with open(bak, "w", encoding="utf-8", newline="") as fh:
                fh.write(old)
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, target)
        self.path = os.path.abspath(target)
        return self.path

    # -- header -------------------------------------------------------------
    @property
    def name(self):
        return self.root.get("name", "")

    @name.setter
    def name(self, v):
        self.root.set("name", str(v))

    @property
    def description(self):
        return self.root.get("description", "")

    @description.setter
    def description(self, v):
        self.root.set("description", str(v))

    @property
    def size(self):
        return (int(_num(self.root.get("width"), 1)), int(_num(self.root.get("length"), 1)))

    # -- component access ---------------------------------------------------
    @property
    def components(self):
        return [Component(self, c) for c in self._components_el.findall("c")]

    @property
    def bridge_components(self):
        return [Component(self, c, bridge=True) for c in self._bridge_el.findall("c")]

    def all_components(self):
        return self.components + self.bridge_components

    def get(self, comp_id, required=True):
        comp_id = int(comp_id)
        for comp in self.all_components():
            if comp.id == comp_id:
                return comp
        if required:
            raise EditError("no component with id %d" % comp_id)
        return None

    def find(self, type=None, label=None, category=None, region=None):
        """Filter components by type / label substring / category / bounding box."""
        spec = find_type(type) if type is not None else None
        out = []
        for comp in self.all_components():
            if spec is not None and comp.type_id != spec.type_id:
                continue
            if category is not None and comp.spec.category != category:
                continue
            if label is not None:
                got = comp.name or ""
                if label.lower() not in got.lower():
                    continue
            if region is not None:
                x0, y0, x1, y1 = region
                x, y = comp.pos
                if not (min(x0, x1) <= x <= max(x0, x1) and min(y0, y1) <= y <= max(y0, y1)):
                    continue
            out.append(comp)
        return out

    # -- id allocation ------------------------------------------------------
    def _next_id(self):
        counter = int(_num(self.root.get("id_counter"), 0))
        used = {c.id for c in self.all_components()}
        nid = max([counter] + list(used)) + 1
        self.root.set("id_counter", str(nid))
        return nid

    def _next_node_id(self):
        counter = int(_num(self.root.get("id_counter_node"), 0))
        used = {int(_num(n.get("id"), 0)) for n in self._nodes_el.findall("n")}
        nid = max([counter] + list(used)) + 1
        self.root.set("id_counter_node", str(nid))
        return nid

    # -- editing ------------------------------------------------------------
    def add(self, type, x=0.0, y=0.0, properties=None, inputs=None, bridge=False):
        """Create a component and return it."""
        table = BRIDGE_TYPES if bridge else COMPONENT_TYPES
        if bridge:
            spec = table[int(type)]
        else:
            spec = find_type(type)
        obj = sxml.Element("object", {"id": "0"})
        obj.append(sxml.Element("pos"))
        c = sxml.Element("c", {} if spec.type_id == 0 else {"type": str(spec.type_id)})
        c.append(obj)
        (self._bridge_el if bridge else self._components_el).append(c)

        comp = Component(self, c, bridge=bridge)
        comp.id = self._next_id()
        comp.pos = (x, y)
        for field, value in (properties or {}).items():
            comp.set_property(field, value)
        for key, src in (inputs or {}).items():
            if isinstance(src, dict):
                comp.connect(key, src["component_id"], src.get("output", 0))
            else:
                comp.connect(key, src)
        self.revision += 1
        return comp

    def remove(self, comp_id, rewire=False):
        """Delete a component.

        ``rewire`` reconnects anything fed by this component to the source of
        its first input, which is what you want when dropping a pass-through
        node out of a chain.
        """
        comp = self.get(comp_id)
        replacement = None
        if rewire:
            own = comp.links()
            for name in comp.link_names():
                link = own.get(name)
                if link:
                    replacement = link
                    break
        removed_inbound = 0
        for other in self.all_components():
            if other.id == comp.id:
                continue
            for name, link in other.links().items():
                if link and link["component_id"] == comp.id:
                    if replacement:
                        other.connect(name, replacement["component_id"], replacement["id"])
                    else:
                        other.disconnect(name)
                    removed_inbound += 1
        parent = self._bridge_el if comp.bridge else self._components_el
        parent.remove(comp.c)
        detached_pins = self._detach_io_nodes(comp.id)
        self.revision += 1
        return {"removed": comp.id, "rewired_inputs": removed_inbound,
                "detached_pins": detached_pins}

    def move(self, comp_id, x=None, y=None, dx=0.0, dy=0.0):
        comp = self.get(comp_id)
        cx, cy = comp.pos
        nx = cx if x is None else float(x)
        ny = cy if y is None else float(y)
        comp.pos = (nx + float(dx), ny + float(dy))
        self.revision += 1
        return comp

    def move_many(self, comp_ids, dx=0.0, dy=0.0):
        moved = []
        for cid in comp_ids:
            moved.append(self.move(cid, dx=dx, dy=dy))
        return moved

    def connect(self, target_id, input, source_id, source_output=0):
        target = self.get(target_id)
        self.get(source_id)  # existence check
        name = target.connect(input, source_id, source_output)
        self.revision += 1
        return name

    def disconnect(self, target_id, input):
        target = self.get(target_id)
        ok = target.disconnect(input)
        self.revision += 1
        return ok

    def set_property(self, comp_id, field, value):
        comp = self.get(comp_id)
        comp.set_property(field, value)
        self.revision += 1
        return comp

    # -- io pins ------------------------------------------------------------
    @property
    def io_pins(self):
        out = []
        for n in self._nodes_el.findall("n"):
            node = n.find("node")
            pos = node.find("position") if node is not None else None
            out.append({
                "id": int(_num(n.get("id"), 0)),
                "component_id": int(_num(n.get("component_id"), 0)),
                "label": node.get("label", "") if node is not None else "",
                "description": node.get("description", "") if node is not None else "",
                "mode": int(_num(node.get("mode"), 0)) if node is not None else 0,
                "type": int(_num(node.get("type"), 0)) if node is not None else 0,
                "x": int(_num(pos.get("x"), 0)) if pos is not None else 0,
                "z": int(_num(pos.get("z"), 0)) if pos is not None else 0,
            })
        return out

    def _detach_io_nodes(self, comp_id):
        removed = []
        for n in list(self._nodes_el.findall("n")):
            if int(_num(n.get("component_id"), -1)) == comp_id:
                self._nodes_el.remove(n)
                removed.append(int(_num(n.get("id"), 0)))
        return removed

    def add_io_pin(self, component_id, label, x=0, z=0, mode=None, type=None,
                   description=None):
        """Expose a bridge component as a pin on the microprocessor's face."""
        comp = self.get(component_id)
        if not comp.bridge:
            raise EditError("component %d is not a bridge component; io pins may only "
                            "reference entries of <components_bridge>" % component_id)
        node = sxml.Element("node", {"label": str(label)})
        if mode is not None:
            node.set("mode", str(int(mode)))
        if type is not None:
            node.set("type", str(int(type)))
        if description:
            node.set("description", str(description))
        pos = sxml.Element("position")
        if int(x):
            pos.set("x", str(int(x)))
        if int(z):
            pos.set("z", str(int(z)))
        node.append(pos)
        n = sxml.Element("n", {"id": "0", "component_id": str(int(component_id))})
        n.append(node)
        self._nodes_el.append(n)
        n.set("id", str(self._next_node_id()))
        self.revision += 1
        return int(n.get("id"))

    # -- state mirror -------------------------------------------------------
    def sync_states(self):
        """Rebuild ``<component_states>`` / ``<component_bridge_states>``.

        The game writes those sections as an exact mirror of ``<components>``
        (``<object>`` renamed to ``<cN>``); keeping them in sync avoids the
        editor seeing a stale snapshot.
        """
        for src_el, dst_tag in ((self._components_el, "component_states"),
                                (self._bridge_el, "component_bridge_states")):
            dst = self.group.ensure(dst_tag)
            dst.clear_children()
            dst.attrib = {}
            for i, c in enumerate(src_el.findall("c")):
                obj = c.find("object")
                if obj is None:
                    continue
                mirror = obj.copy()
                mirror.tag = "c%d" % i
                dst.append(mirror)
        self.group.ensure("group_states")
        return self

    # -- analysis -----------------------------------------------------------
    def validate(self):
        """Return a list of problems; empty means the document is consistent."""
        issues = []
        ids = {}
        for comp in self.all_components():
            if comp.id in ids:
                issues.append({"level": "error", "component": comp.id,
                               "message": "duplicate component id %d" % comp.id})
            ids[comp.id] = comp
            table = BRIDGE_TYPES if comp.bridge else COMPONENT_TYPES
            if comp.type_id not in table:
                issues.append({"level": "error", "component": comp.id,
                               "message": "unknown %s type %d"
                                          % ("bridge" if comp.bridge else "component",
                                             comp.type_id)})
        for comp in self.all_components():
            for name, link in comp.links().items():
                if not link:
                    continue
                src = ids.get(link["component_id"])
                if src is None:
                    issues.append({"level": "error", "component": comp.id,
                                   "message": "%s points at missing component %d"
                                              % (name, link["component_id"])})
                    continue
                want = self._input_dtype(comp, name)
                got = self._output_dtype(src, link["id"])
                if want is not None and got is not None and want != got:
                    issues.append({
                        "level": "warning", "component": comp.id,
                        "message": "%s expects %s but component %d outputs %s"
                                   % (name, DATA_TYPE.get(want, want),
                                      src.id, DATA_TYPE.get(got, got))})
        for pin in self.io_pins:
            if pin["component_id"] not in ids:
                issues.append({"level": "error", "component": pin["component_id"],
                               "message": "io pin %d (%r) references missing component %d"
                                          % (pin["id"], pin["label"], pin["component_id"])})
        counter = int(_num(self.root.get("id_counter"), 0))
        if ids and max(ids) > counter:
            issues.append({"level": "warning", "component": None,
                           "message": "id_counter is %d but the highest component id is %d"
                                      % (counter, max(ids))})
        return issues

    @staticmethod
    def _input_dtype(comp, link_name):
        names = comp.link_names()
        if link_name not in names:
            return None
        idx = names.index(link_name)
        if comp.spec.variadic_inputs:
            if link_name == "inc":
                return 5
            return 1 if comp.type_id == 40 else 0
        if idx < len(comp.spec.inputs):
            return comp.spec.inputs[idx][1]
        return None

    @staticmethod
    def _output_dtype(comp, out_index):
        outs = comp.spec.outputs
        if out_index < len(outs):
            return outs[out_index][1]
        return None

    def summary(self):
        by_type = {}
        for comp in self.components:
            by_type[comp.spec.name] = by_type.get(comp.spec.name, 0) + 1
        xs = [c.pos[0] for c in self.components] or [0]
        ys = [c.pos[1] for c in self.components] or [0]
        return {
            "name": self.name,
            "description": self.description,
            "width": self.size[0],
            "length": self.size[1],
            "components": len(self.components),
            "bridge_components": len(self.bridge_components),
            "io_pins": len(self.io_pins),
            "bounds": {"min_x": min(xs), "max_x": max(xs),
                       "min_y": min(ys), "max_y": max(ys)},
            "by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
            "path": self.path,
        }

    def graph(self):
        """Adjacency list: ``{component_id: [ids it feeds]}``."""
        out = {c.id: [] for c in self.all_components()}
        for comp in self.all_components():
            for link in comp.links().values():
                if link and link["component_id"] in out:
                    out[link["component_id"]].append(comp.id)
        return out

    def free_position(self, near=(0.0, 0.0), step=1.25, spacing=1.0):
        """Find an unoccupied spot near ``near`` (spiral search on a grid)."""
        taken = {(round(c.pos[0], 3), round(c.pos[1], 3)) for c in self.components}
        cx, cy = float(near[0]), float(near[1])
        ring = 0
        while ring < 64:
            for dx in range(-ring, ring + 1):
                for dy in range(-ring, ring + 1):
                    if ring and max(abs(dx), abs(dy)) != ring:
                        continue
                    p = (round(cx + dx * step, 3), round(cy + dy * step, 3))
                    if all(abs(p[0] - t[0]) >= spacing or abs(p[1] - t[1]) >= spacing
                           for t in taken):
                        return p
            ring += 1
        return (cx, cy)

    def __repr__(self):
        return "<Microprocessor %r %d components>" % (self.name, len(self.components))
