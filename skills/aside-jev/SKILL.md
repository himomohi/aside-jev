---
name: aside-jev
description: Use when driving Aside with TypeSafe Jev bounded decisions — app owns candidate action IDs, Jev picks one, Aside executes, caller verifies. Prefer over free-form computer-use when actions can be enumerated.
---

# aside-jev

Keep the decision layer **above** Aside. Aside observes and executes; your app
builds complete candidates; TypeSafe Jev returns **one candidate id**.

Never let Jev invent selectors, tool names, URLs, or arguments.

## Install

```bash
uv tool install "aside-jev @ git+https://github.com/himomohi/aside-jev"
# or: pip install -e .
aside-jev serve   # MCP stdio
```

Register MCP:

```json
{
  "mcpServers": {
    "aside-jev": {
      "command": "aside-jev",
      "args": ["serve"],
      "env": { "TYPESAFE_API_KEY": "${TYPESAFE_API_KEY}" }
    },
    "aside": { "command": "aside", "args": ["mcp"] }
  }
}
```

## Loop

1. Observe with Aside (`aside mcp` / REPL).
2. Build a bounded candidate table (each row = full tool + args). Always include `abstain`.
3. Call `jev_step` or `jev_choose` (`provider=mock|live`).
4. Fail closed on unknown ids (`jev_validate`).
5. Execute at most one Aside action from the original table.
6. Verify an independent postcondition (DOM value, `/state`, API), not the model text.

## Safety

- Mock path must work without `TYPESAFE_API_KEY`.
- Live key only from env / secure prompt — never argv, source, or logs.
- Snapshot-bound refs die after the page changes — rebuild the table.
