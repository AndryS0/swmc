# swmc — Stormworks microprocessor XML parser, editor and MCP server

Read, edit and serve the `.xml` files that Stormworks writes for microcontrollers.

Every component type, field name and data type in this package was recovered from
`stormworks64.exe` rather than guessed from sample files — see
[Provenance](#provenance). CPython 3.8+, no packages to install.

```
swmc/
  nodetypes.py   generated tables: 60 component types + 10 bridge pin types
  sxml.py        format-preserving XML reader/writer for this specific dialect
  model.py       Microprocessor / Component object model and editing operations
  watch.py       polling file watcher for realtime updates
  server.py      MCP server (JSON-RPC over stdio, no SDK dependency)
  webui.py       HTTP + SSE backend for the browser editor
  static/        the editor: index.html, app.js (canvas), lua.js (script view),
                 luaapi.js (Lua API reference), style.css
                 vendor/luaparse.js -- the only third-party code in the project
  cli.py         command line front end
tests/           96 tests, run against a real 124-component microprocessor
```

Everything except `static/vendor/luaparse.js` is standard library only; that one
file is vendored rather than installed, so there is still nothing to `pip` or
`npm` before running this.

## Graphical editor

```bash
python -m swmc.webui --file "Complex Helicopter Gyro.xml"
```

Opens your default browser (Firefox, Edge, anything — it is an ordinary local
web page) on a node-graph view of the circuit.

- **Pan** drag the background · **Zoom** wheel · **Fit** `F`
- **Select** click, shift-click to add, drag the background to marquee,
  `Ctrl+A` for all
- **Move** drag; everything selected moves together and snaps to the 0.25 grid
- **Wire** drag from an output pin to an input pin. Drag a wire off an input to
  re-aim it, drop it on empty space to delete it, or double-click it.
- **Add** drag a component from the left palette onto the canvas, or click it to
  drop one in the middle
- **Delete** `Delete` on the selection or a selected wire
- **Properties** the right panel is built from the type's real field list, so a
  Lua component gets a script box, a clamp gets min/max, a function block gets
  its formula. Number fields accept expressions (`1/3`, `2*pi`) and show the
  evaluated result.
- **Undo/redo** `Ctrl+Z` / `Ctrl+Shift+Z` · **Save** `Ctrl+S` (autosave is on
  anyway) · **Validate** lists problems and clicking one jumps to it

Pin and wire colours follow the signal type, matching the in-game node colours,
with a legend along the bottom of the canvas:

| signal | colour | |
|---|---|---|
| on/off | red | `--dt-bool` |
| number | green | `--dt-number` |
| composite | purple | `--dt-composite` |
| video | blue | `--dt-video` |
| audio | orange | `--dt-audio` |

Change them in `static/style.css`; a test checks that every type the engine can
emit has a colour and that no two share one. Hovering a pin names its signal
type in words, so colour is never the only cue.

The dot in the title bar turns green when the live connection is up; when the
file changes underneath you — because you saved in-game, or an agent edited it —
the canvas updates by itself.

### Lua view

The **Lua** button in the toolbar (or double-clicking a Lua Script node) opens a
dedicated editing view — the inspector's cramped textarea is no place to work on
a 90-line script.

| | |
|---|---|
| `Ctrl+Space` | completion (also opens as you type) |
| `Ctrl+F`, `F3`, `Shift+F3` | find, next, previous |
| `Ctrl+/` | toggle comment on the selected lines |
| `Tab`, `Shift+Tab` | indent / outdent, across a multi-line selection |
| `Ctrl+S` | save now (it autosaves anyway) |
| `Esc` | back to the canvas |

**Highlighting** covers Lua itself plus the game's API globals (`input`,
`output`, `screen`, `property`, `map`, `async`) and the
`onTick`/`onDraw`/`httpReply` callbacks, each in their own colour. An
unterminated string is underlined where it breaks.

**Completion** offers members after a dot (`screen.` lists every draw call with
its parameters), and for a bare word it offers keywords, API globals, callbacks
and *identifiers already in your script*, so local names complete too. Accepting
a call selects its parameter list so you can type over it.

**Checks** land in a Problems panel; clicking one jumps to it. Highlighting is
instant, analysis is debounced ~350ms so half-typed code does not flash errors.

Syntax comes from a **real Lua parser** —
[luaparse](https://github.com/fstirlitz/luaparse) 0.3.1 (MIT), vendored under
`static/vendor/`. The game embeds **Lua 5.3** (its `_VERSION` string sits at
`0x140ade5d8` in `stormworks64.exe`, right beside the Lua error messages), so
the parser is configured for exactly that: `//`, `<<`, `~`, `goto` all parse.
A parser is the only way to catch things a token count cannot see —

```
a =            →  <expression> expected near '<eof>'     (line 1, column 4)
if a = b then  →  unexpected symbol '=' near '='
f(1, )         →  <expression> expected near ')'
```

On top of the AST sit the checks that need to know about *this* game and *this*
microprocessor:

- a composite channel outside `1..32`
- `screen.*` called from `onTick`, or `input`/`output` from `onDraw` — both do
  nothing there. Scope comes from the AST, so a helper called *by* `onDraw` is
  not mistaken for being inside it.
- a member that is not part of the Stormworks API, with a suggestion
  (`screen.drawSquare` → *did you mean drawRect, drawRectF?*)
- a global that is read but never assigned anywhere — catches `outpout.setNumber`
  and friends. Assigned globals are fine; keeping state in globals between ticks
  is ordinary Stormworks style.
- a script that defines neither `onTick` nor `onDraw`
- **`property.getNumber("X")` where no property component on this
  microprocessor is labelled `X`**, listing the labels that do exist — and
  **`property.getNumber` on a Property Toggle**, which tells you to use
  `getBool`. Only possible because the Lua view and the canvas share one
  document.

Running this over the sample's own script found a real bug in it: line 86 reads
a bare `ws` that is never assigned anywhere — a typo for `wsT` — so `wsOld` is
`nil` on every tick. `tests/lua_logic.js` pins that as a regression test.

The reference in `static/luaapi.js` was compiled from the Japanese community
wiki at <https://wikiwiki.jp/sbarjp/> (「Luaスクリプト」 and 「Lua例文集」), which
documents the API more completely than the in-game tooltips.

`tests/lua_logic.js` runs the shipped highlighter, analyzer and completion in a
Node VM. The highlighter must round-trip exactly — stripping the markup returns
the source, including `<`, `>` and `&` — and the analyzer must report **no
syntax errors** on the sample's real 94-line script.

### Labels

A component box is only 1.25 × 0.5 grid units, so names are word-wrapped over
several lines at the largest font size that still shows the whole name. Wrapping
breaks after commas as well as spaces, which is what lets
`Boolean f(x,y,z,w,a,b,c,d)` fit — a test checks that all 69 component and pin
names do. Hovering a node shows its full name, its type and the type's
description regardless.

**Roomy** spreads the drawn layout to twice the spacing and enlarges the boxes
so names sit on two or three comfortable lines. It changes only the rendering —
saved coordinates are untouched — and because the gaps grow with the boxes, the
tightest real layouts still do not overlap.

`Flip Y` mirrors the vertical axis if the layout reads upside-down compared to
the in-game editor. Both toggles are remembered per browser.

The editor and the MCP server can share one process, so an agent and a human can
work on the same document at the same time: call the `gui_open` tool, or start
the MCP server and open the URL it reports.


## Quick start

```bash
python -m swmc.cli info      "Complex Helicopter Gyro.xml"
python -m swmc.cli types     --category composite
python -m swmc.cli describe  func8
python -m swmc.cli validate  "Complex Helicopter Gyro.xml"
python -m swmc.cli watch     "Complex Helicopter Gyro.xml"
```

```python
from swmc import Microprocessor

doc = Microprocessor.load("Complex Helicopter Gyro.xml")

a = doc.add("const", x=50, y=50, properties={"n": 2})
b = doc.add("func8", x=52, y=50, properties={"e": "x*pi"})
doc.connect(b.id, "in1", a.id)          # or doc.connect(b.id, 1, a.id)
doc.move(b.id, dx=1.25)
doc.set_property(a.id, "n", {"text": "1/3", "value": 0.333333})
doc.remove(a.id, rewire=True)

print(doc.validate())
doc.save()                               # atomic replace, states kept in sync
```

## MCP server

```bash
python -m swmc.server                                  # stdio
python -m swmc.server --file "path/to/Gyro.xml"        # pre-open a document
python -m swmc.server --no-autosave --poll-interval 1  # batch-friendly
```

Register it for Claude Code (a `.mcp.json` doing this already sits in the parent
directory):

```json
{
  "mcpServers": {
    "stormworks": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "swmc.server"],
      "env": { "PYTHONPATH": "E:/temp/stormworks/swmc" }
    }
  }
}
```

### Tools

| Tool | Purpose |
|---|---|
| `open` / `close` / `list_open` | Document lifecycle; opening starts the file watcher |
| `summary` | Name, size, counts, bounds, per-type histogram |
| `list_types` / `describe_type` | Browse the 60 component types; inputs, outputs, properties |
| `list_components` / `get_component` | Query by type, label, category or bounding box |
| `io_pins` | The `<nodes>` section and the bridge component each pin binds to |
| `trace` | Walk the signal graph upstream or downstream, level by level |
| `validate` | Dangling links, duplicate ids, orphaned pins, wire type mismatches |
| `add_component` / `remove_component` | Create and delete, with optional `rewire` splice-out |
| `move_component` | Absolute `x`/`y`, relative `dx`/`dy`, one id or a list |
| `connect` / `disconnect` | Wiring, by `in2` / index / input label |
| `set_property` / `set_header` | Component fields, microprocessor name and description |
| `add_io_pin` | Expose a bridge component on the microprocessor's face |
| `batch` | Many edits, one undo step, all-or-nothing |
| `save` / `reload` / `undo` / `redo` | |
| `poll_changes` / `set_autosave` | Realtime — see below |
| `gui_open` / `gui_status` / `gui_close` | Launch the browser editor on the same live document |
| `raw_xml` | Literal XML of a component or the whole file, for anything unmodelled |

Open documents are also exposed as MCP **resources**, and the server emits
`notifications/resources/updated` to subscribers when a file changes underneath it.

### Realtime behaviour

* **Autosave is on by default** — every edit is written to disk immediately, so
  reopening the microcontroller in-game shows the change. Writes go to a temp
  file and are then `os.replace`d, so the game never sees a half-written file.
* A background thread polls every watched file (0.4 s default, size + mtime +
  SHA-1) and:
  * **clean document** → reloads it automatically and records the event;
  * **unsaved edits** → flags a conflict instead of silently discarding either
    side. `save(force=true)` keeps yours, `reload(force=true)` keeps theirs.
    Every tool result carries a warning banner while a conflict is outstanding.
* Writes made *by the server* are fingerprinted and never reported back as
  external changes.
* `poll_changes` drains the event queue, so a client with no notification
  support can still follow along.

Polling rather than `watchdog`/`ReadDirectoryChangesW` is deliberate: no
dependency, and it behaves the same on network shares and synced folders where
native notifications are unreliable.

## The XML format

```xml
<microprocessor name="…" width="5" length="3" id_counter="972" id_counter_node="64" …>
  <nodes>                          <!-- pins on the outside of the block -->
    <n id="3" component_id="7">
      <node label="Pilot seat" mode="1" type="5"/>
      …
  <group>
    <data><inputs/><outputs/></data>
    <components>                   <!-- the logic itself -->
      <c type="36">
        <object id="772" e="a*clamp(x+z*y,-1,1)">
          <pos x="4.75" y="7.5"/>
          <in1 component_id="771"/>
          …
    <components_bridge>            <!-- one entry per external pin -->
    <component_states>             <!-- exact mirror of <components> -->
    <component_bridge_states>
    <group_states/>
```

Points that matter when writing this format:

* **`<c>` with no `type` attribute is type 0 (NOT).**
* `<component_states>` is a byte-for-byte mirror of `<components>` with
  `<object>` renamed to `<c0>`, `<c1>`, … `save()` regenerates it; a test
  asserts that regenerating it on a file the game wrote reproduces the file
  exactly.
* `id_counter` is the highest component id in use; new ids come from it.
* Zero coordinates are omitted: `<pos y="6"/>`, not `<pos x="0" y="6"/>`.
* Link elements carry `component_id` plus an optional `id` naming which output
  of the source to take (`0`, the first output, is omitted).
* **Attribute values contain raw newlines and tabs** inside `script="…"`.
  `xml.etree.ElementTree` normalises those to spaces per the XML spec, which
  flattens a Lua script onto one line and changes its meaning. That is why
  `sxml.py` exists; `tests/test_roundtrip.py::test_lua_script_survives` pins it.

### Field encodings

`nodetypes.py` records, per type, how each field is stored — derived from which
serializer helper the binary calls:

| Kind | XML shape | Binary helper |
|---|---|---|
| `link` | `<in1 component_id="42"/>` | `sub_140905430` (number/bool), `sub_140906030` (composite/video/audio) |
| `attr_str` | `e="x+y"` on `<object>` | `sub_1408F3380` |
| `attr_int` | `i="10"` | `sub_1408EF630`, `sub_1408EF890`, `sub_14094B6C0` (`m`), `sub_14094B910` (`u`) |
| `attr_float` | `ct="2"` | `sub_1408EFD50` |
| `prop_num` | `<min text="-0.1" value="-0.1"/>` | `sub_140904130` |
| `state_out`, `state` | only inside `<component_states>` | `sub_140905680`, `sub_140192E90` |

`prop_num` keeps `text` (what the player typed, possibly an expression) separate
from `value` (its evaluated result), and `set_property` accepts either a number
or `{"text": …, "value": …}`.

Anything not modelled — dropdown `<items>`, future fields — is preserved
verbatim through a load/save cycle, so this library can never silently drop data
it does not understand.

## Provenance

Extracted from `stormworks64.exe` (imagebase `0x140000000`):

| What | Where |
|---|---|
| Component definition table | `qword_140D1B088`, built by `sub_140367330` |
| Table layout | 60 entries × 128 bytes; `entry = table + (type << 7)` |
| Entry fields | `+0` type id, `+4` category, `+32` name, `+48` description, `+64` inputs, `+88` outputs |
| `<c type="N">` → object factory | `sub_14038BD80` (60 cases) |
| `components_bridge` factory | `sub_14038CA00` (10 cases) |
| Reads the `type` attribute | `sub_1409077B0`, called from `sub_14038B940` |
| Per-type XML serializer | vtable slot 5 of each `c_microprocessor_component_*` class |
| Mesh name by type | `sub_140370140` |
| Category name by id | `sub_14036FFF0` |
| Input-link serializer | `sub_140370910` (`id`, `component_id`, `built_slot_index`) |

The type-id ordering is confirmed twice over: by the explicit `entry[+0] = N`
stores in the initializer, and independently by the 60-case mesh-name switch.

`../stormworks_microprocessor_node_types.json` holds the same data as plain JSON.

## Tests

```bash
python -m unittest discover -s tests -t .
```

Round-trip fidelity, schema completeness (every attribute and child element in
the sample file must be modelled), all editing operations, validation, the MCP
server driven over real stdio including the realtime conflict paths, and the web
backend over real HTTP including server-sent events.

There is no headless browser here, so the front end is covered two ways instead
of pretending otherwise: a static audit (`test_frontend.py`) that every element
id, CSS class, API route, batch op and tool name the JavaScript reaches for
actually exists on the other side, and `frontend_logic.js`, which loads the
shipped `app.js` into a Node VM behind a stub DOM and exercises its real
geometry, snapping and expression-evaluation code. Clicking around in a browser
is still the last mile.

By default the tests read the sample from
`C:\Users\andry\Downloads\Complex Helicopter Gyro.xml`; point `SWMC_SAMPLE` at
another microprocessor to run them against it.
