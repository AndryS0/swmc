# Examples

Each file runs on its own and prints what it did:

```bash
python examples/01_inspect.py            "Complex Helicopter Gyro.xml"
python examples/02_build_from_scratch.py out.xml
python examples/03_edit_in_place.py      "Complex Helicopter Gyro.xml" out.xml
python examples/04_edit_lua.py           "Complex Helicopter Gyro.xml"
python examples/05_watch.py              "Complex Helicopter Gyro.xml"
python examples/06_mcp_client.py         "Complex Helicopter Gyro.xml"
```

Every example that writes takes an output path and never touches its input, so
you can point them at a real microcontroller from
`%APPDATA%\Stormworks\data\microprocessors\` without risk.

| | |
|---|---|
| `01_inspect.py` | load, summarise, filter, follow the signal graph, validate |
| `02_build_from_scratch.py` | `Microprocessor.new()` → components → wiring → an external pin |
| `03_edit_in_place.py` | retune an existing circuit and splice a node into a wire |
| `04_edit_lua.py` | read and rewrite a Lua Script component's source |
| `05_watch.py` | react to the game saving the file under you |
| `06_mcp_client.py` | drive the MCP server over stdio, as an agent would |

`tests/test_examples.py` runs all of them, so they cannot silently rot.
