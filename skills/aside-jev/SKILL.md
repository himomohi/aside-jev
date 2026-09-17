---
name: aside-jev
description: Use when an Aside agent should decide with TypeSafe Jev (System One) — Choice/Score/Noul or bounded action IDs — instead of free-form LLM clicks. Prefer over inventing selectors.
---

# aside-jev

**Jev is the decision model. Aside is the browser runtime.**

Jev (TypeSafe System One) returns typed answers only: `Choice`, `Score`, `Noul`. It does not generate text or invent tool calls. Aside observes and executes.

## When to use

- Pick next macro-step / tool / candidate id with calibrated confidence
- Gate risky clicks (`Score` / `Noul` thresholds in *your* code)
- Keep selectors and tool args **app-owned**, never model-invented

## Install / MCP

```bash
uv tool install "aside-jev @ git+https://github.com/himomohi/aside-jev"
export TYPESAFE_API_KEY=…
aside-jev serve
```

Register `aside-jev` **beside** `aside` in MCP config. Live needs `TYPESAFE_API_KEY` (or `TYPESAFEAI_API_KEY`). Mock needs none.

## Loop

1. Observe with Aside (`aside mcp` / REPL).
2. Either:
   - call `jev_system_one` with Choice/Score/Noul on the observation state, or
   - build a candidate action table (always include `abstain`) and call `jev_step` / `jev_choose`.
3. Fail closed on unknown ids (`jev_validate`).
4. Execute at most one Aside action from the original table.
5. Verify an independent postcondition (DOM / API), not model text.

## Do not

- Treat this as a Cua / computer-use driver
- Let Jev invent selectors, URLs, or tool names
- Skip confidence thresholds on destructive actions
