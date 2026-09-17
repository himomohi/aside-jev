# aside-jev

**Let [Aside](https://aside.com) agents decide with [TypeSafe Jev](https://typesafe.ai) — not with free-form LLM clicks.**

[Jev](https://docs.typesafe.ai/introduction) is TypeSafe’s **System One** model: it does **not** generate text. You send `state` + typed questions (`Choice` / `Score` / `Noul`) and get calibrated values your code can branch on (typically **70–500ms**).

`aside-jev` wires that model into Aside workflows as an MCP server + skill:

1. **Aside** observes / executes the browser (`aside mcp`).
2. **Your agent** builds the decision (state + questions, or an app-owned action table).
3. **Jev** returns a typed answer (e.g. one candidate id).
4. **Your agent** executes only that answer via Aside, then verifies independently.

> This is **not** a Cua integration. Cua’s *jev-use* demo is just one recipe that also calls Jev.  
> Here the runtime is **Aside**; the decision model is **Jev**.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-stdio-111111.svg)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## Why Jev (not another chat model)

| | Chat / computer-use LLM | **Jev (System One)** |
| --- | --- | --- |
| Output | Prose / invented tool calls | Typed `Choice` / `Score` / `Noul` only |
| Hallucinated selectors | Common | **Impossible** if options are app-owned |
| Latency | Seconds | ~70–500ms |
| Confidence | Soft / uncalibrated | Calibrated probabilities |

Docs: [Introduction](https://docs.typesafe.ai/introduction) · [Python SDK](https://docs.typesafe.ai/sdk/python) · API `POST /v1/systemone`

---

## Install

```bash
uv tool install "aside-jev @ git+https://github.com/himomohi/aside-jev"
# or
git clone https://github.com/himomohi/aside-jev.git
cd aside-jev && ./scripts/install.sh
```

```bash
export TYPESAFE_API_KEY=…   # also accepts TYPESAFEAI_API_KEY
```

Mock path needs **no** key (CI / demos).

### MCP next to Aside

```json
{
  "mcpServers": {
    "aside": { "command": "aside", "args": ["mcp"] },
    "aside-jev": {
      "command": "aside-jev",
      "args": ["serve"],
      "env": { "TYPESAFE_API_KEY": "${TYPESAFE_API_KEY}" }
    }
  }
}
```

On this machine a wrapper `~/.local/bin/aside-jev-mcp` can source `~/.config/typesafe/api.env` then run `aside-jev serve`.

Skill: `skills/aside-jev/` → copied to `~/.aside/skills/` by `scripts/install.sh`.

---

## MCP tools

| Tool | What Jev does |
| --- | --- |
| `jev_system_one` | General System One call — mix Choice / Score / Noul on one state |
| `jev_choose` | Choice over an **app-owned** candidate action table (`mock` \| `live`) |
| `jev_validate` | Fail closed if id ∉ table |
| `jev_step` | choose + confidence gate + `execute` payload for Aside |

### General decisions (`jev_system_one`)

```json
{
  "state": { "url": "…", "goal": "submit form", "snapshot": "…" },
  "questions": {
    "done": { "type": "noul", "instructions": "The form is already submitted" },
    "risk": {
      "type": "score",
      "instructions": "How risky is the next click",
      "criteria": ["safe", "reversible", "destructive"]
    },
    "next": {
      "type": "choice",
      "instructions": "Best next macro-step",
      "criteria": {
        "fill_fields": "Fill empty required fields",
        "submit": "Submit the form",
        "stop": "Stop and ask the user"
      }
    }
  }
}
```

### Action IDs for Aside (`jev_choose` / `jev_step`)

Your agent enumerates **complete** actions (tool + args). Jev only returns one **id**. Aside runs that row. Unknown ids fail closed. Always include `abstain`.

```bash
aside-jev choose \
  --goal "fill the verification field" \
  --candidates examples/demo_candidates.json \
  --observation examples/demo_observation.json \
  --provider mock \
  --prefer type-verification-value
```

---

## Safety model

1. **App owns options** — Choice criteria / candidate rows are defined in code.
2. **Jev returns values** — never selectors, never free tool names.
3. **Validate before execute** — unknown id → error / abstain.
4. **Threshold in your code** — use `confidence` / `noul` bands (auto / confirm / human).
5. **Verify independently** — DOM / API / `/state`, not model prose.
6. **Keys in env only** — never argv, source, or logs.

---

## Development

```bash
uv sync --extra dev
uv run pytest -q
```

Python ≥ 3.11 · MIT · depends on [`typesafe-sdk`](https://pypi.org/project/typesafe-sdk/) (`TypeSafeClient.system_one`, model `jev-latest`).

---

## Related

- TypeSafe Jev docs: https://docs.typesafe.ai  
- Aside browser agent: `aside mcp` / `aside repl`  
- Cua *jev-use* is an **unrelated** demo that also calls Jev with a different executor — not required here.
