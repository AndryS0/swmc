"""Build a working microcontroller from nothing and save it.

    python examples/02_build_from_scratch.py out.xml

Makes a throttle conditioner: a number input is scaled by a property slider,
offset by a trim slider, clamped to 0..1, and sent to a number output pin. Drop
the result in %APPDATA%\\Stormworks\\data\\microprocessors\\ and it will open in
the game.
"""

import sys

from swmc import Microprocessor


def main(out_path):
    doc = Microprocessor.new(
        name="Throttle conditioner",
        description="Scales and trims a throttle signal, clamped to 0..1.",
        width=2, length=1,
    )

    # ---- external input pin ------------------------------------------------
    # An external pin is two objects: a bridge component that carries the
    # signal, and a <nodes> entry that puts it on the block's face. Bridge
    # types are 0/1 bool in/out, 2/3 number, 4/5 composite, 6/7 video,
    # 8/9 audio -- so 2 is "number input".
    pin_in = doc.add(2, bridge=True, x=-8, y=0)
    doc.add_io_pin(pin_in.id, "Throttle in", x=0, z=0, type=1,
                   description="Raw throttle, 0..1")

    # ---- the circuit -------------------------------------------------------
    # Properties appear on the microcontroller's panel once it is on a vehicle.
    gain = doc.add("slider", -5, -2, properties={
        "name": "Gain", "min": 0, "max": 2, "int": 0.05, "v": 1})
    trim = doc.add("slider", -5, 2, properties={
        "name": "Trim", "min": -0.25, "max": 0.25, "int": 0.01, "v": 0})

    scaled = doc.add("mul", -2, -1)
    doc.connect(scaled.id, 1, pin_in.id)
    doc.connect(scaled.id, 2, gain.id)

    trimmed = doc.add("add", 1, 0)
    doc.connect(trimmed.id, 1, scaled.id)
    doc.connect(trimmed.id, 2, trim.id)

    # Number properties accept a plain number, or {"text": ..., "value": ...}
    # when you want to keep the expression a player typed.
    limited = doc.add("clamp", 4, 0, properties={"min": 0, "max": 1})
    # connect() takes "in1", the index 1, or the input's own label.
    doc.connect(limited.id, "Input Number", trimmed.id)

    # ---- external output pin ----------------------------------------------
    pin_out = doc.add(3, bridge=True, x=8, y=0)     # 3 = number output
    doc.connect(pin_out.id, "in1", limited.id)
    doc.add_io_pin(pin_out.id, "Throttle out", x=1, z=0, type=1)

    # ---- check before writing ---------------------------------------------
    issues = doc.validate()
    for i in issues:
        print("  %-8s %s" % (i["level"], i["message"]))
    if any(i["level"] == "error" for i in issues):
        print("refusing to save a broken microprocessor")
        return 1

    doc.save(out_path)
    print("wrote %s" % out_path)
    print("  %d components (%d of them external pins), %d io pins"
          % (len(doc), len(doc.bridge_components), len(doc.io_pins)))
    for c in doc.components:
        print("    #%-4d %-20s at (%g, %g)%s"
              % (c.id, c.spec.name, c.pos[0], c.pos[1],
                 "  %r" % c.label if c.label else ""))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
