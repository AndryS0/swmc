"""Read a microprocessor: summarise it, filter it, follow its wiring, check it.

    python examples/01_inspect.py "Complex Helicopter Gyro.xml"

Nothing here writes to disk.
"""

import sys

from swmc import DATA_TYPE, Microprocessor


def main(path):
    doc = Microprocessor.load(path)

    # ---- the shape of the thing -------------------------------------------
    s = doc.summary()
    print("%s  (%d x %d)" % (s["name"] or "(unnamed)", s["width"], s["length"]))
    if s["description"]:
        print("  %s" % s["description"])
    print("  %d components, %d bridge pins, %d external io pins"
          % (s["components"], s["bridge_components"], s["io_pins"]))
    print("  five most used types:")
    for name, count in list(s["by_type"].items())[:5]:
        print("    %-30s %d" % (name, count))

    # A Microprocessor is a container: len(), iteration, `id in doc`, doc[id].
    print("  len(doc) counts bridge pins too: %d" % len(doc))

    # ---- filtering ---------------------------------------------------------
    # find() takes a type (id, alias or display name), a label substring, a
    # category, or a bounding box.
    sliders = doc.find(type="slider")
    print("\nproperty sliders (%d):" % len(sliders))
    for c in sliders[:5]:
        p = c.properties()
        print("  #%-4d %-24s %s..%s" % (
            c.id, c.label, p.get("min", {}).get("text", "?"),
            p.get("max", {}).get("text", "?")))

    print("\ncomponents in the top-left quadrant: %d"
          % len(doc.find(region=(-100, -100, 0, 0))))

    # ---- following a signal ------------------------------------------------
    # Wires point backwards: a component records what feeds its inputs. To find
    # consumers, use the graph.
    pins = doc.io_pins
    if pins:
        pin = pins[0]
        print("\nexternal pin %r is bound to component #%d"
              % (pin["label"], pin["component_id"]))
        carrier = doc.get(pin["component_id"], required=False)
        if carrier:
            for field, link in carrier.links().items():
                if link:
                    src = doc.get(link["component_id"], required=False)
                    print("  it reads %s from #%d (%s)"
                          % (field, link["component_id"],
                             src.spec.name if src else "?"))

    feeds = doc.graph()
    busiest = max(feeds, key=lambda k: len(feeds[k]))
    c = doc[busiest]
    print("\n#%d (%s) feeds %d other components"
          % (c.id, c.spec.name, len(feeds[busiest])))

    # ---- what a type can do ------------------------------------------------
    spec = doc[busiest].spec
    print("\n%s — %s" % (spec.name, spec.description))
    for field, (label, dt) in zip(spec.link_fields, spec.inputs):
        print("  in  %-6s %-22s %s" % (field, label, DATA_TYPE.get(dt, "?")))
    for i, (label, dt) in enumerate(spec.outputs):
        print("  out #%-5d %-22s %s" % (i, label, DATA_TYPE.get(dt, "?")))

    # ---- consistency -------------------------------------------------------
    issues = doc.validate()
    errors = [i for i in issues if i["level"] == "error"]
    print("\nvalidate: %d error(s), %d warning(s)" % (errors and len(errors) or 0,
                                                      len(issues) - len(errors)))
    for i in issues[:5]:
        print("  %-8s %s" % (i["level"], i["message"]))
    return 1 if errors else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
