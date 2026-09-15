"""Retune an existing microprocessor without disturbing the rest of it.

    python examples/03_edit_in_place.py "Complex Helicopter Gyro.xml" out.xml

Shows the three edits you actually reach for: change a property, splice a new
component into an existing wire, and remove a component while keeping the
signal flowing through it.

The input file is never modified.
"""

import sys

from swmc import Microprocessor


def main(in_path, out_path):
    doc = Microprocessor.load(in_path)
    before = len(doc)

    # ---- 1. change a property ---------------------------------------------
    sliders = doc.find(type="slider")
    if sliders:
        s = sliders[0]
        old = s.properties().get("max", {}).get("text")
        s.set_property("max", 8)
        print("slider %r: max %s -> %s"
              % (s.label, old, s.properties()["max"]["text"]))

    # ---- 2. splice a component into a wire --------------------------------
    # Find something that feeds an external output pin, and put a clamp between
    # them. Wires point backwards, so "splice" means: rewire the consumer to
    # read from the new component, and point the new component at the old
    # source.
    target = None
    for pin in doc.io_pins:
        carrier = doc.get(pin["component_id"], required=False)
        if carrier is None:
            continue
        link = carrier.links().get("in1")
        if link:
            target = (carrier, link["component_id"], pin["label"])
            break

    if target:
        carrier, source_id, label = target
        x, y = carrier.pos
        limiter = doc.add("clamp", x - 2, y, properties={"min": -1, "max": 1})
        doc.connect(limiter.id, "in1", source_id)     # new <- old source
        doc.connect(carrier.id, "in1", limiter.id)    # consumer <- new
        print("spliced a clamp between #%d and the %r pin (new #%d)"
              % (source_id, label, limiter.id))

    # ---- 3. remove a component, keeping the chain intact -------------------
    # rewire=True reconnects whatever read this component to whatever fed its
    # first input, which is what you want when dropping a pass-through out of a
    # chain. Without it the consumers are simply left unwired.
    passthrough = next((c for c in doc.components
                        if c.spec.name == "Abs" and c.links().get("in1")), None)
    if passthrough:
        info = doc.remove(passthrough.id, rewire=True)
        print("removed #%d (Abs), rewiring %d consumer(s)"
              % (info["removed"], info["rewired_inputs"]))

    # ---- save --------------------------------------------------------------
    issues = doc.validate()
    errors = [i for i in issues if i["level"] == "error"]
    if errors:
        for i in errors:
            print("  error   %s" % i["message"])
        return 1

    doc.save(out_path)
    print("wrote %s  (%d components, was %d)" % (out_path, len(doc), before))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
