# Stormworks microprocessor tooling

Everything needed to read, edit and reason about the `.xml` files Stormworks
writes for microcontrollers — as a Python library, an MCP server, a browser
editor, and a Claude Code skill.

The component tables were **reverse engineered from `stormworks64.exe`** rather
than inferred from sample files, so type ids, field names, data types and the
Lua version are exact. See [Provenance](#provenance).

```
.
├── .claude/skills/                 Claude Code skill + node-type reference
├── stormworks_microprocessor_node_types.json
│                                   the extracted tables as plain JSON
└── swmc/                           the implementation -> swmc/README.md
    ├── LICENSE                     MIT, plus luaparse's notice
    └── examples/                   six runnable scripts
```

Nothing is registered or installed by default. See
[As an MCP server](#as-an-mcp-server) to wire it into Claude Code.

---

## What is here

### `swmc/` — library, MCP server and editor

The whole implementation. **See [`swmc/README.md`](swmc/README.md)** for the API,
the XML format notes, the reverse-engineering addresses and the test layout.

In short:

| | |
|---|---|
| **Library** | `Microprocessor.load()` / `.add()` / `.connect()` / `.save()`, round-trip exact, fully typed |
| **MCP server** | 30 tools over stdio, zero dependencies |
| **Browser editor** | node-graph canvas + a Lua script view with real static analysis |
| **CLI** | `python -m swmc.cli` — `info`, `list`, `show`, `types`, `describe`, `validate`, `watch` |
| **Tests** | 120, run against a real 124-component microprocessor |

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

The server is not registered anywhere by default — add it once, in whichever
scope you want.

#### Installed (recommended)

```bash
pip install ./swmc          # or -e ./swmc to keep editing in place
```

That puts `swmc`, `swmc-server` and `swmc-gui` on PATH, which makes the config
short and machine-independent:

```jsonc
{
  "mcpServers": {
    "stormworks": {
      "type": "stdio",
      "command": "swmc-server",
      "env": { "PYTHONUTF8": "1" }
    }
  }
}
```

If Claude Code cannot find `swmc-server`, give the absolute path to it —
`pip show -f swmc` locates it, and inside a virtualenv it is
`…/Scripts/swmc-server.exe` or `…/bin/swmc-server`.

#### Straight from the source tree

No install, but the config has to do the work:

```jsonc
{
  "mcpServers": {
    "stormworks": {
      "type": "stdio",
      "command": "C:/Users/you/AppData/Local/Programs/Python/Python310/python.exe",
      "args": ["-m", "swmc.server"],
      "env": {
        "PYTHONPATH": "E:/temp/stormworks/swmc",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

- **`command` must be an absolute path to a Python 3.8+ interpreter.** A bare
  `python` works only if it resolves for the process that spawns the server,
  which is not a given on Windows where `python` is often a shim.
- **`PYTHONPATH` points at the outer `swmc/` directory** — the one *containing*
  the `swmc` package, not the package itself. Get it one level too deep and you
  get `No module named 'swmc'`.

In both cases **`PYTHONUTF8=1`** keeps the server reading and writing UTF-8
whatever the system code page. Without it a microprocessor whose name or Lua
script holds non-ASCII text can fail to load on a non-UTF-8 Windows locale.

#### Scope, and checking it worked

Put that JSON in `.mcp.json` next to this README for this directory only, or add
the `"stormworks"` entry to `mcpServers` in `~/.claude.json` to have it
everywhere. Restart Claude Code and approve `stormworks` when prompted; `/mcp`
lists the connected servers.

If it does not appear, run the command by hand — it should sit waiting on stdin
and print `[swmc] ready on stdio; 30 tools` to stderr.

With it connected, ask for what you want in plain language — the skill in
`.claude/skills/` covers the workflow.

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

```bash
pip install ./swmc
```

```python
from swmc import Microprocessor

doc = Microprocessor.new("Gain stage")     # or .load("Gyro.xml")
gain = doc.add("slider", x=0, y=0, properties={"name": "Gain", "min": 0, "max": 4})
clamp = doc.add("clamp", x=2, y=0, properties={"min": -1, "max": 1})
doc.connect(clamp.id, "Input Number", gain.id)
print(doc.validate())
doc.save("Gain stage.xml")
```

`swmc/examples/` has six runnable scripts covering inspection, building from
scratch, editing in place, rewriting a Lua component, watching for the game's
saves, and driving the MCP server. All of them are run by the test suite.

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

Everything here was read out of one specific build:

| | |
|---|---|
| Game | Stormworks: Build and Rescue **v1.15.23** |
| Binary | `stormworks64.exe`, 13,944,320 bytes |
| SHA-256 | `f9206d85c82f4d02fd0ac391781d19c5c68394a9ffc48accca0e1f5966db8699` |
| SHA-1 | `c47322a8934cdbf73e8b1b9c06d3aa43c650a2fb` |
| MD5 | `db15f7abf04ffde1b5c596a41e823c63` |
| Imagebase | `0x140000000` |
| Embedded Lua | 5.3 |

The exe carries no PE version resource and its PE timestamp is `0xFFFFFFFF` (a
reproducible build), so the version comes from the binary itself: `WinMain`
stores the literal `"Stormworks"` and `"v1.15.23"` into adjacent globals at
startup, the latter at `0x140B0F498`.

To check your own copy:

```powershell
(Get-FileHash "…\Stormworks\stormworks64.exe" -Algorithm SHA256).Hash
```

Type ids have been stable across updates in practice, and a new component type
would be appended rather than renumbered — but if your hash differs and
something looks wrong, that is the first thing to suspect.

Addresses within the binary:

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

120 tests: byte-exact XML round trip, schema completeness, every editing
operation, the MCP server over real stdio, the web backend over real HTTP
including server-sent events, and the editor's JavaScript run in a Node VM.

By default they read the sample from
`C:\Users\andry\Downloads\Complex Helicopter Gyro.xml`; point `SWMC_SAMPLE` at
another microprocessor to run them against it.
