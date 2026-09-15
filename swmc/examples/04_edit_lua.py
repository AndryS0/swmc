"""Read and rewrite the source of a Lua Script component.

    python examples/04_edit_lua.py "Complex Helicopter Gyro.xml" [out.xml]

Without an output path it only reads.

The script lives in the ``script`` property of a type 56 component. It is a
plain string with real newlines and tabs -- which is exactly why this library
exists: a spec-conformant XML parser normalises those to spaces and quietly
flattens the whole script onto one line.
"""

import sys

from swmc import Microprocessor


TEMPLATE = """-- written by examples/04_edit_lua.py
ticks = 0

function onTick()
\tticks = ticks + 1
\tgain = property.getNumber('Gain')
\toutput.setNumber(1, input.getNumber(1) * gain)
\toutput.setBool(1, ticks %% 60 < 30)
end
"""


def main(in_path, out_path=None):
    doc = Microprocessor.load(in_path)

    scripts = doc.find(type="lua")
    if not scripts:
        print("no Lua Script component in this microprocessor")
        return 0

    for c in scripts:
        src = c.properties().get("script", "")
        lines = src.split("\n")
        print("#%d at (%g, %g): %d chars, %d lines"
              % (c.id, c.pos[0], c.pos[1], len(src), len(lines)))
        print("  newlines survived the load:", "\n" in src)
        print("  first line: %s" % (lines[0][:70] if lines else ""))

        # Which callbacks does it define, and what does it touch?
        for probe in ("onTick", "onDraw", "screen.", "property.get"):
            print("  %-14s %s" % (probe, "yes" if probe in src else "no"))

    if not out_path:
        return 0

    # ---- rewrite the first one --------------------------------------------
    target = scripts[0]
    doc.set_property(target.id, "script", TEMPLATE)

    # Property labels referenced from Lua must match a property component, or
    # property.getNumber returns nil at runtime. The editor's Lua view checks
    # this for you; here it is by hand.
    labels = {c.label for c in doc.components
              if c.spec.category == "property" and c.label}
    for want in ("Gain",):
        print("  property %r exists: %s" % (want, want in labels))
        if want not in labels:
            doc.add("prop_number", *doc.free_position(near=target.pos),
                    properties={"n": want, "v": 1})
            print("    added a Property Number labelled %r" % want)

    doc.save(out_path)
    reloaded = Microprocessor.load(out_path)
    got = reloaded[target.id].properties()["script"]
    print("wrote %s" % out_path)
    print("  script round-tripped byte for byte:", got == TEMPLATE)
    print("  tabs and newlines intact:", "\t" in got and "\n" in got)
    return 0


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
