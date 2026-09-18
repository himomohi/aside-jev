---
name: aside-jev
description: REQUIRED for Aside browse / computer-use. Decide every browser step with TypeSafe Jev (Choice/Score/Noul or action IDs); Aside only executes. Never invent selectors.
---

# aside-jev (Aside browse → Jev)

**Jev decides. Aside browses.**

Aside’s chat model must not free-form invent the next click. On every browse / Ultrabrowse / computer-use step:

1. Observe with Aside.
2. Build a full candidate table (tool + args) yourself; always include `abstain`.
3. Call Jev via the absolute CLI from AGENTS.md (`aside-jev choose` or `aside-jev system-one`).
4. Execute only the returned id with Aside.
5. Verify independently (DOM/API).

## CLI

```bash
# absolute path is written into ~/.aside/u/0/AGENTS.md by install.sh
aside-jev choose --goal '…' --candidates cands.json --observation obs.json --provider live
aside-jev system-one --state state.json --questions questions.json
aside-jev serve   # MCP for Cursor / external agents
```

Live needs `TYPESAFE_API_KEY` (or `~/.config/typesafe/api.env`). Mock needs none.

## MCP tools

`jev_system_one` · `jev_choose` · `jev_validate` · `jev_step`

## Do not

- Skip Jev and invent CSS/xpath/coordinates for the next action
- Treat this as a Cua driver — runtime is Aside; model is Jev
