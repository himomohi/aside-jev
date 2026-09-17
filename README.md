# aside-jev

**Bounded decisions for Aside browser agents.**

Your app owns the action table. [TypeSafe Jev](https://typesafe.ai) picks **one ID**. Aside executes it. You verify with an independent check — not the model’s prose.

> Free-form computer-use invents clicks.  
> **aside-jev** only returns an ID you already defined.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-stdio-111111.svg)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## Why

Agents that emit raw `click(x,y)` / invented selectors drift. The [CUA × TypeSafe jev-use](https://github.com/trycua/cua) pattern flips the contract:

| Layer | Owns |
| --- | --- |
| **Your app** | Complete candidates (`id` → tool + args) |
| **Jev** | One choice among those IDs (+ confidence) |
| **Aside** | Observe + execute |
| **You** | Independent `/state` / DOM / API verify |

Unknown IDs fail closed. Always include `abstain`.

```text
┌─────────────┐     candidates      ┌──────────┐     choice_id     ┌─────────┐
│  Your agent │ ──────────────────► │ aside-jev│ ────────────────► │  Aside  │
│  (observe)  │ ◄────────────────── │  + Jev   │                   │ execute │
└─────────────┘   independent verify└──────────┘                   └─────────┘
```

---

## Install

```bash
# from GitHub
uv tool install "aside-jev @ git+https://github.com/himomohi/aside-jev"

# or clone
git clone https://github.com/himomohi/aside-jev.git
cd aside-jev && ./scripts/install.sh
```

Live path needs a TypeSafe key (never commit it):

```bash
export TYPESAFE_API_KEY=…   # also accepts TYPESAFEAI_API_KEY
```

Mock path works with **zero** credentials — CI-friendly.

### MCP next to Aside

```json
{
  "mcpServers": {
    "aside": {
      "command": "aside",
      "args": ["mcp"]
    },
    "aside-jev": {
      "command": "aside-jev",
      "args": ["serve"],
      "env": {
        "TYPESAFE_API_KEY": "${TYPESAFE_API_KEY}"
      }
    }
  }
}
```

Skill ships in `skills/aside-jev/` and is copied by `scripts/install.sh` into `~/.aside/skills/` (+ AGENTS.md markers).

---

## Quickstart

```bash
aside-jev choose \
  --goal "fill the verification field" \
  --candidates examples/demo_candidates.json \
  --observation examples/demo_observation.json \
  --provider mock \
  --prefer type-verification-value
```

```json
{
  "choice_id": "type-verification-value",
  "confidence": 1.0,
  "candidate": {
    "id": "type-verification-value",
    "tool": "aside_type",
    "arguments": { "selector": "#verification", "text": "{{token}}", "replace": true }
  }
}
```

### MCP tools

| Tool | Job |
| --- | --- |
| `jev_choose` | Pick one candidate id (`mock` \| `live`) |
| `jev_validate` | Fail closed if id ∉ table |
| `jev_step` | Choose + confidence gate + `execute` payload for Aside |

### Python loop

```python
from aside_jev.core import Candidate, build_abstain
from aside_jev.loop import LoopConfig, run_bounded_loop

steps = run_bounded_loop(
    config=LoopConfig(goal="submit form", provider="mock", max_steps=5),
    observe=lambda: {"url": "...", "fields": {}},
    propose=lambda obs: [
        Candidate("type-email", "Type email", tool="type", arguments={"text": "a@b.c"}),
        build_abstain(),
    ],
    execute=lambda c: print("run", c.tool, c.arguments),
    verify=lambda: "verified",
)
```

---

## Safety model

1. **App owns the table** — every row is a complete, executable action.
2. **Jev returns an ID only** — no selectors, no tool invention.
3. **Validate before execute** — unknown id → error / abstain.
4. **Verify independently** — DOM value, API, or `/state`, never model text.
5. **Snapshot-bound refs** — after the page changes, rebuild candidates.
6. **Keys stay in env** — never argv, source, or logs.

---

## CLI

```bash
aside-jev --version
aside-jev serve                 # MCP stdio
aside-jev choose --goal … --candidates … [--provider mock|live]
```

---

## Development

```bash
uv sync --extra dev
uv run pytest -q
```

Python ≥ 3.11. MIT licensed.

---

## Credits

Inspired by [CUA Driver](https://github.com/trycua/cua) **jev-use** (TypeSafe Jev × computer-use). This package ports the same bounded-decision contract to **Aside** agents and MCP.

Not affiliated with TypeSafe or CUA — just the same good idea, wired for Aside.
