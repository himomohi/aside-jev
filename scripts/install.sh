#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${ASIDE_JEV_HOME:-$HOME/.aside/extensions/aside-jev}"
mkdir -p "$DEST" "$HOME/.aside/skills" "$HOME/.agents/skills" 2>/dev/null || true

if command -v uv >/dev/null 2>&1; then
  uv tool install --force --editable "$ROOT" || uv pip install --python "$(which python3)" -e "$ROOT"
else
  python3 -m pip install --user -e "$ROOT"
fi

cp -R "$ROOT/skills/aside-jev" "$HOME/.aside/skills/aside-jev" 2>/dev/null || true
cp -R "$ROOT/skills/aside-jev" "$HOME/.agents/skills/aside-jev" 2>/dev/null || true
rsync -a --delete --exclude .venv --exclude .git "$ROOT/" "$DEST/" 2>/dev/null || cp -R "$ROOT"/. "$DEST/"

# Absolute CLI path for Aside agents (do not rely on PATH — same pattern as aside-codemode)
ASIDE_JEV_BIN="$(command -v aside-jev || true)"
if [[ -z "$ASIDE_JEV_BIN" && -x "$HOME/.local/bin/aside-jev" ]]; then
  ASIDE_JEV_BIN="$HOME/.local/bin/aside-jev"
fi
if [[ -z "$ASIDE_JEV_BIN" ]]; then
  ASIDE_JEV_BIN="$HOME/.local/bin/aside-jev"
fi

# Wrapper that loads TypeSafe key then serves / chooses
WRAPPER="$HOME/.local/bin/aside-jev-mcp"
cat > "$WRAPPER" <<WRAP
#!/bin/bash
set -euo pipefail
ENV_FILE="\${HOME}/.config/typesafe/api.env"
if [[ -f "\$ENV_FILE" ]]; then set -a; # shellcheck disable=SC1090
  source "\$ENV_FILE"; set +a; fi
if [[ -z "\${TYPESAFE_API_KEY:-}" && -n "\${TYPESAFEAI_API_KEY:-}" ]]; then
  export TYPESAFE_API_KEY="\$TYPESAFEAI_API_KEY"
fi
exec "${ASIDE_JEV_BIN}" serve
WRAP
chmod +x "$WRAPPER"

# Browse-step helper: loads env, runs choose
BROWSE="$HOME/.local/bin/aside-jev-browse"
cat > "$BROWSE" <<WRAP
#!/bin/bash
set -euo pipefail
ENV_FILE="\${HOME}/.config/typesafe/api.env"
if [[ -f "\$ENV_FILE" ]]; then set -a; # shellcheck disable=SC1090
  source "\$ENV_FILE"; set +a; fi
if [[ -z "\${TYPESAFE_API_KEY:-}" && -n "\${TYPESAFEAI_API_KEY:-}" ]]; then
  export TYPESAFE_API_KEY="\$TYPESAFEAI_API_KEY"
fi
exec "${ASIDE_JEV_BIN}" "\$@"
WRAP
chmod +x "$BROWSE"

MARKER_BEGIN="# BEGIN aside-jev"
MARKER_END="# END aside-jev"
BLOCK=$(cat <<MD
# BEGIN aside-jev
## aside-jev — REQUIRED for Aside browse / computer-use

Jev (TypeSafe System One) is the **decision model**. Aside is only the **browser runtime**.
For **every** browser step (navigate, click, type, select, submit, hover-to-act, fill):

1. Observe with Aside tools (snapshot / a11y / URL / fields).
2. Build a complete candidate table yourself (each row = full tool + args). Always include \`abstain\`.
3. Ask Jev — do **not** invent the next selector yourself. Call the absolute CLI (never PATH lookup):

\`\`\`bash
${ASIDE_JEV_BIN} choose --goal '<goal>' --candidates <cands.json> --observation <obs.json> --provider live
\`\`\`

   General gates (done? risky?) use:

\`\`\`bash
${ASIDE_JEV_BIN} system-one --state <state.json> --questions <questions.json>
\`\`\`

4. Execute **only** the returned \`choice_id\` row via Aside. Unknown id → \`abstain\`.
5. Verify with an independent check (DOM/API), not model prose.

Never free-form invent CSS selectors, coordinates, or tool names for the next action.
Mock: \`--provider mock\` (no key). Live: \`TYPESAFE_API_KEY\` or \`~/.config/typesafe/api.env\`.
MCP (Cursor/external): \`aside-jev\` / \`${WRAPPER}\` exposes \`jev_system_one\`, \`jev_choose\`, \`jev_validate\`, \`jev_step\`.
# END aside-jev
MD
)

for AGENTS in \
  "$HOME/.aside/u/0/AGENTS.md" \
  "$HOME/.aside/AGENTS.md" \
  "$HOME/AGENTS.md"
 do
  dir=$(dirname "$AGENTS")
  mkdir -p "$dir" 2>/dev/null || continue
  touch "$AGENTS"
  python3 - "$AGENTS" "$BLOCK" <<'PY'
import pathlib,re,sys
path=pathlib.Path(sys.argv[1])
block=sys.argv[2]
if not block.endswith("\n"):
    block+="\n"
text=path.read_text() if path.exists() else ""
if "# BEGIN aside-jev" in text:
    new=re.sub(r"# BEGIN aside-jev.*?# END aside-jev\n?", block, text, flags=re.S)
else:
    new=text.rstrip()+"\n\n"+block
path.write_text(new)
print("updated", path)
PY
done

echo "aside-jev extension → $DEST"
echo "CLI → $ASIDE_JEV_BIN"
echo "browse wrapper → $BROWSE"
"$ASIDE_JEV_BIN" --version || true
