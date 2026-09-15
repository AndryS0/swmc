"""Command line front end -- handy for inspecting files without an MCP client.

    python -m swmc.cli info      "Gyro.xml"
    python -m swmc.cli list      "Gyro.xml" --type func8
    python -m swmc.cli show      "Gyro.xml" 528
    python -m swmc.cli types     --query pid
    python -m swmc.cli validate  "Gyro.xml"
    python -m swmc.cli watch     "Gyro.xml"
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from .model import Microprocessor
from .nodetypes import (
    ALIASES,
    BRIDGE_TYPES,
    COMPONENT_TYPES,
    DATA_TYPE,
    DATA_TYPE_SHORT,
    find_type,
)
from .watch import FileWatcher


def cmd_info(args):
    doc = Microprocessor.load(args.file)
    s = doc.summary()
    print("%s  (%dx%d)" % (s["name"] or "(unnamed)", s["width"], s["length"]))
    if s["description"]:
        print("  %s" % s["description"])
    print("  %d components, %d bridge pins, %d io pins"
          % (s["components"], s["bridge_components"], s["io_pins"]))
    b = s["bounds"]
    print("  bounds x[%g..%g] y[%g..%g]"
          % (b["min_x"], b["max_x"], b["min_y"], b["max_y"]))
    print("  most used:")
    for name, count in list(s["by_type"].items())[:12]:
        print("    %-30s %d" % (name, count))
    return 0


def cmd_list(args):
    doc = Microprocessor.load(args.file)
    comps = doc.find(type=args.type, label=args.label, category=args.category)
    for c in comps:
        links = ", ".join("%s<-%d" % (k, v["component_id"])
                          for k, v in c.links().items() if v)
        print("%6d  %-28s (%7.2f,%7.2f)  %s%s"
              % (c.id, c.spec.name, c.pos[0], c.pos[1],
                 ("%r " % c.name) if c.name else "", links))
    print("-- %d components" % len(comps))
    return 0


def cmd_show(args):
    doc = Microprocessor.load(args.file)
    c = doc.get(args.id)
    print(json.dumps(c.to_dict(), indent=2))
    return 0


def cmd_types(args):
    table = BRIDGE_TYPES if args.bridge else COMPONENT_TYPES
    for t in table.values():
        if args.category and t.category != args.category:
            continue
        if args.query:
            aliases = " ".join(a for a, i in ALIASES.items() if i == t.type_id)
            hay = ("%s %s %s %s" % (t.type_id, t.name, t.cls, aliases)).lower()
            if args.query.lower() not in hay:
                continue
        ins = ",".join(DATA_TYPE_SHORT.get(dt, "?") for _l, dt in t.inputs)
        outs = ",".join(DATA_TYPE_SHORT.get(dt, "?") for _l, dt in t.outputs)
        props = ",".join(f for f, k in t.design_fields if k != "link")
        print("%3d  %-28s %-10s in[%s] out[%s] %s"
              % (t.type_id, t.name, t.category, ins, outs, props))
    return 0


def cmd_describe(args):
    t = find_type(args.type)
    print("type %d  %s" % (t.type_id, t.name))
    print("  class    : %s" % t.cls)
    print("  category : %s" % t.category)
    print("  mesh     : %s" % t.mesh)
    print("  %s" % t.description)
    for i, name in enumerate(t.link_fields):
        label, dt = t.inputs[i] if i < len(t.inputs) else ("", None)
        print("  in  %-6s %-24s %s" % (name, label, DATA_TYPE.get(dt, "")))
    for i, (label, dt) in enumerate(t.outputs):
        print("  out #%-4d %-24s %s" % (i, label, DATA_TYPE.get(dt, "")))
    for f, k in t.design_fields:
        if k != "link":
            print("  prop %-8s %s" % (f, k))
    return 0


def cmd_validate(args):
    doc = Microprocessor.load(args.file)
    issues = doc.validate()
    for i in issues:
        print("%-8s %s" % (i["level"], i["message"]))
    errors = sum(1 for i in issues if i["level"] == "error")
    print("-- %d error(s), %d warning(s)" % (errors, len(issues) - errors))
    return 1 if errors else 0


def cmd_watch(args):
    w = FileWatcher(args.interval)
    for f in args.file:
        w.watch(f)
    print("watching %d file(s); Ctrl-C to stop" % len(args.file))
    try:
        while True:
            for ev in w.poll_once():
                print("%s  %-9s %s" % (time.strftime("%H:%M:%S"), ev["kind"], ev["path"]))
                if ev["kind"] != "deleted":
                    try:
                        doc = Microprocessor.load(ev["path"])
                        print("           %d components, %d io pins"
                              % (len(doc.components), len(doc.io_pins)))
                    except Exception as exc:
                        print("           unreadable: %s" % exc)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(prog="swmc", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("info", help="summarise a microprocessor")
    p.add_argument("file")
    p.set_defaults(fn=cmd_info)

    p = sub.add_parser("list", help="list components")
    p.add_argument("file")
    p.add_argument("--type")
    p.add_argument("--label")
    p.add_argument("--category")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("show", help="dump one component as JSON")
    p.add_argument("file")
    p.add_argument("id", type=int)
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("types", help="list the component type catalogue")
    p.add_argument("--query")
    p.add_argument("--category")
    p.add_argument("--bridge", action="store_true")
    p.set_defaults(fn=cmd_types)

    p = sub.add_parser("describe", help="detail one component type")
    p.add_argument("type")
    p.set_defaults(fn=cmd_describe)

    p = sub.add_parser("validate", help="check links, ids and data types")
    p.add_argument("file")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("watch", help="print file changes as they happen")
    p.add_argument("file", nargs="+")
    p.add_argument("--interval", type=float, default=0.4)
    p.set_defaults(fn=cmd_watch)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
