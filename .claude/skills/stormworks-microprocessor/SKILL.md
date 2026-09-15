---
name: stormworks-microprocessor
description: Read, inspect and edit Stormworks microcontroller/microprocessor XML files through the `stormworks` MCP server - add or remove logic components, wire them together, move them on the canvas, change properties, manage external IO pins, and validate the result. Use whenever the user mentions a Stormworks microprocessor, microcontroller, logic gate layout, a `.xml` under Stormworks/data/microprocessors, or asks about component "type" numbers like `<c type="36">`.
---

# Editing Stormworks microprocessors

The `stormworks` MCP server edits the `.xml` files Stormworks writes for
microcontrollers. Component tables were reverse engineered from
`stormworks64.exe`, so type ids, field names and data types are exact rather
than guessed.

## Graphical editor

`gui_open()` launches a browser node-graph editor on the same in-memory
document these tools act on, so you and the user can work on it together — your
edits appear on their canvas immediately and theirs appear in your next read.
Open it whenever the user wants to *see* the circuit, asks to arrange or wire
things by hand, or says "show me". `gui_status()` tells you if it is already
running; don't launch it twice.

Once it is open, prefer describing where something is ("the new clamp is at
14.75, 5.5, just left of the tail-rotor pin") over dumping ids.

It has a dedicated **Lua view** (toolbar button, or double-click a Lua Script
node) with highlighting, completion, live checks and a searchable API reference.
When the user wants to work on a script by hand, point them there rather than
pasting a long script into chat.

The view parses with a real Lua 5.3 parser and reports syntax errors with line
and column, plus game-specific checks: channel out of range, drawing from
`onTick`, a `property.get*` label matching no component (or the wrong getter for
that component's type), and globals that are read but never assigned. After you
write or edit a script, suggest they open it and glance at the Problems panel.

## Writing Lua

The Lua Script component is type 56; its code lives in the `script` property
(`set_property(id, "script", "...")`). Read it first with `get_component` — it
is easy to clobber 90 lines by accident.

Key points of the microcontroller API:

- `onTick()` runs 60x/s and owns `input.getNumber/getBool(1..32)` and
  `output.setNumber/setBool(1..32)`; `screen.*` does nothing here.
- `onDraw()` runs per connected monitor and owns `screen.*`; `input`/`output`
  do nothing here.
- `property.getNumber/getBool/getText(label)` reads a Property component by its
  label — the label must match the component's `n`/`name` exactly.
- A monitor feeds its state in on composite: numbers 1-2 are the resolution,
  3-6 the touch position, and bools 1-2 the touch states.

`swmc/static/luaapi.js` holds the full reference (compiled from
<https://wikiwiki.jp/sbarjp/>) if you need a signature.

## Always start here

1. `open(path=...)` — everything else defaults to the single open document.
   Files normally live in
   `%APPDATA%\Stormworks\data\microprocessors\*.xml`.
2. `summary()` — orient yourself: component count, bounding box, type histogram.
3. Only then start editing.

**Edits autosave to disk immediately.** The game does not hot-reload, so tell
the user to reopen the microcontroller in-game to see changes. If they had it
open in the editor and save from the game, your next tool call reports the
external write and reloads automatically.

## Finding the right component type

Never guess a type number. `list_types(query=...)` searches all 60; then
`describe_type(type=...)` gives the exact input names, their data types and the
editable property fields. `type` accepts an id (`36`), an alias (`func8`,
`and`, `pid`, `lua`) or the display name (`"f(x, y, z, w, a, b, c, d)"`).

`reference/node-types.md` has the whole table if you want it in one read.

## Wiring

`connect(target=, input=, source=)` where `input` is `"in2"`, the index `2`, or
the input's label (`"Input Number"`). `source` is the component id whose output
you are taking; add `source_output=1` for the second output of a component that
has two (Divide, SR Latch, JK Flip Flop, Numerical Junction, Lua Script).

Wires always point **backwards**: a component records what feeds *its* inputs.
There is no "output list", so to find consumers use `get_component(id).feeds` or
`trace(id, direction="downstream")`.

## Building a circuit

Use `batch` for anything more than one or two edits. It applies everything under
a single undo step and rolls the whole thing back if any operation fails, so the
file on disk is never left half-built:

```json
{"operations": [
  {"op": "add_component", "type": "const", "x": 20, "y": 20, "properties": {"n": 2}},
  {"op": "add_component", "type": "mul",   "x": 22, "y": 20},
  {"op": "connect", "target": "<id of mul>", "input": 1, "source": "<id of const>"}
]}
```

Add the components in one batch, read the ids out of the result, then wire them
in a second batch. Positions are free-form floats on the same grid the in-game
editor uses; the game's own layouts step by 0.25. `auto_place=true` nudges a new
component to the nearest free slot near `(x, y)`.

## Properties

`set_property(id=, properties={...})` sets several at once. Kinds come from
`describe_type`:

- `attr_str` — text: `{"e": "clamp(x+y,-1,1)"}`, `{"script": "<lua>"}`
- `attr_int` / `attr_float` — numbers: `{"i": 3}`, `{"t": 0.5}`
- `prop_num` — takes a plain number, or `{"text": "1/3", "value": 0.333333}`
  when you want to preserve the expression the player typed

Function blocks (`func1`/`func3`/`func8`, `bfunc4`/`bfunc8`) put their formula
in `e`. Variables are `x, y, z, w, a, b, c, d` matching `in1..in8`.

## External IO pins

The pins on the outside of the block are two objects: an entry in
`components_bridge` (the signal carrier) and an entry in `<nodes>` (the visible
pin). To add one:

1. `add_component(type=<bridge type>, bridge=true, x=, y=)` — bridge types are
   0/1 bool in/out, 2/3 number in/out, 4/5 composite, 6/7 video, 8/9 audio
   (`list_types(bridge=true)`).
2. `connect(...)` your logic into it (for an output pin) or connect it into your
   logic (for an input pin).
3. `add_io_pin(component_id=<the bridge id>, label=..., x=, z=)` where `x`/`z`
   are the slot on the block face.

Deleting a bridge component detaches its pin automatically.

## Before you finish

Run `validate()`. Errors (dangling links, duplicate ids, orphaned pins) mean the
file is broken. Warnings are data-type mismatches on a wire — an on/off signal
feeding a number input usually means the wrong input index.

Report what changed in terms the user recognises: component labels and what the
circuit now does, not raw ids.

## When something is not modelled

`raw_xml(id=...)` returns a component's literal XML. Unmodelled structures
(dropdown `<items>`, anything added by a future game update) round-trip
untouched, so they are safe to leave alone — but they cannot be edited through
typed tools.

## Gotchas

- `<c>` with no `type` attribute is type 0 (NOT), not "no type".
- Component ids are global across `components` and `components_bridge`.
- Lua scripts contain real newlines inside the `script` attribute. Never
  hand-edit these files with a generic XML tool — a spec-conformant parser
  flattens the script to one line. Use this server.
- `undo` history is dropped when the file changes on disk externally.
- If the user has unsaved in-game edits and you also edit, the server reports a
  conflict instead of picking a winner. Ask the user which side to keep:
  `save(force=true)` keeps yours, `reload(force=true)` keeps theirs.
