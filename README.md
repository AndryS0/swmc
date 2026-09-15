# Stormworks microprocessor tooling

Everything needed to read, edit and reason about the `.xml` files Stormworks
writes for microcontrollers — as a Python library, an MCP server, a browser
editor, and a Claude Code skill.

The component tables were **reverse engineered from `stormworks64.exe`** rather
than inferred from sample files, so type ids, field names, data types and the
Lua version are exact. See [Provenance](#provenance).

```
.
├── .mcp.json                       MCP server registration (project-scoped)
├── .claude/skills/                 Claude Code skill + node-type reference
├── stormworks_microprocessor_node_types.json
│                                   the extracted tables as plain JSON
└── swmc/                           the implementation -> swmc/README.md
```

---

## What is here

### `swmc/` — library, MCP server and editor

The whole implementation. **See [`swmc/README.md`](swmc/README.md)** for the API,
the XML format notes, the reverse-engineering addresses and the test layout.

In short:

| | |
|---|---|
| **Library** | `Microprocessor.load()` / `.add()` / `.connect()` / `.save()`, round-trip exact |
| **MCP server** | 30 tools over stdio, zero dependencies |
| **Browser editor** | node-graph canvas + a Lua script view with real static analysis |
| **CLI** | `python -m swmc.cli` — `info`, `list`, `show`, `types`, `describe`, `validate`, `watch` |
| **Tests** | 96, run against a real 124-component microprocessor |

CPython 3.8+ and nothing to install. The one piece of third-party code —
[luaparse](https://github.com/fstirlitz/luaparse) (MIT), used to parse Lua — is
vendored under `swmc/swmc/static/vendor/`.

### `stormworks_microprocessor_node_types.json`

The extracted tables as data, for anything that is not Python: all 60 component
types and 10 bridge pin types with their names, categories, meshes, C++ class
names, input/output labels and data types, plus the XML field schema and the
binary addresses each fact came from.

### `.claude/skills/stormworks-microprocessor/`

A Claude Code skill that teaches the workflow: open a file first, look types up
instead of guessing a number, wire with `connect`, batch multi-step edits, run
`validate` before finishing, and the gotchas that bite (a `<c>` with no `type`
attribute is type 0, not "no type"; Lua scripts hold real newlines inside an XML
attribute, so a generic XML tool flattens them).

[`reference/node-types.md`](.claude/skills/stormworks-microprocessor/reference/node-types.md)
beside it is the full 60-type table in one readable page — input names and data
types, outputs, editable property fields, aliases.

It is project-scoped. To use it from anywhere, move the directory to
`~/.claude/skills/`.

---

## Using it

### As an MCP server

`.mcp.json` registers the server for this directory. Start Claude Code here and
approve `stormworks`; then ask for what you want in plain language — the skill
covers the rest.

```jsonc
{
  "mcpServers": {
    "stormworks": {
      "type": "stdio",
      "command": "…/python.exe",
      "args": ["-m", "swmc.server"],
      "env": { "PYTHONPATH": "…/swmc" }
    }
  }
}
```

To make it global instead, copy that entry into `mcpServers` in
`~/.claude.json`.

The 30 tools cover the document (`open`, `summary`, `save`, `reload`,
`poll_changes`), the catalogue (`list_types`, `describe_type`), queries
(`list_components`, `get_component`, `io_pins`, `trace`, `validate`,
`raw_xml`), edits (`add_component`, `remove_component`, `move_component`,
`connect`, `disconnect`, `set_property`, `set_header`, `add_io_pin`, `batch`,
`undo`, `redo`) and the editor (`gui_open`, `gui_status`, `gui_close`).

### As a graphical editor

```bash
cd swmc
python -m swmc.webui --file "%APPDATA%/Stormworks/data/microprocessors/Your.xml"
```

Opens in your default browser — an ordinary local page, any browser works. Drag
components from the palette, wire output pins to input pins, edit properties,
and open the **Lua** view for scripts.

Or call the `gui_open` tool: the editor then shares one live document with the
agent, so edits from either side show up on both immediately.

### As a library

```python
from swmc import Microprocessor

doc = Microprocessor.load("Gyro.xml")
gain = doc.add("slider", x=20, y=20, properties={"name": "Gain", "min": 0, "max": 4})
clamp = doc.add("clamp", x=22, y=20, properties={"min": -1, "max": 1})
doc.connect(clamp.id, "Input Number", gain.id)
print(doc.validate())
doc.save()
```

---

## Realtime

Edits autosave to disk, written to a temp file and then `os.replace`d so the
game never sees a half-written file. A background thread watches every open
file; when it changes underneath you — you saved in-game, or an agent edited it
— a clean document reloads itself and the browser canvas updates, while a
document with unsaved edits raises a conflict rather than silently picking a
winner.

Stormworks does not hot-reload, so reopen the microcontroller in-game to see
changes.

---

## Provenance

Extracted from `stormworks64.exe` (imagebase `0x140000000`):

| What | Where |
|---|---|
| Component definition table | `qword_140D1B088`, built by `sub_140367330` |
| Table layout | 60 entries × 128 bytes; `entry = table + (type << 7)` |
| `<c type="N">` → object factory | `sub_14038BD80` (60 cases) |
| `components_bridge` factory | `sub_14038CA00` (10 cases) |
| Reads the `type` attribute | `sub_1409077B0`, from `sub_14038B940` |
| Per-type XML field schema | vtable slot 5 of each `c_microprocessor_component_*` |
| Mesh name by type | `sub_140370140` |
| Category name by id | `sub_14036FFF0` |
| Lua version (`5.3`) | `_VERSION` string at `0x140ade5d8` |

The type-id ordering is confirmed twice over: by the explicit `entry[+0] = N`
stores in the initializer, and independently by the 60-case mesh-name switch.
`swmc/README.md` has the field-encoding details.

---

## Tests

```bash
cd swmc
python -m unittest discover -s tests -t .
```

96 tests: byte-exact XML round trip, schema completeness, every editing
operation, the MCP server over real stdio, the web backend over real HTTP
including server-sent events, and the editor's JavaScript run in a Node VM.

By default they read the sample from
`C:\Users\andry\Downloads\Complex Helicopter Gyro.xml`; point `SWMC_SAMPLE` at
another microprocessor to run them against it.
