#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${ASIDE_JEV_HOME:-$HOME/.aside/extensions/aside-jev}"
mkdir -p "$DEST" "$HOME/.aside/skills" "$HOME/.agents/skills" 2>/dev/null || true

# Install package for current user
if command -v uv >/dev/null 2>&1; then
  uv tool install --force --editable "$ROOT" || uv pip install --python "$(which python3)" -e "$ROOT"
else
  python3 -m pip install --user -e "$ROOT"
fi

# Skill copies
cp -R "$ROOT/skills/aside-jev" "$HOME/.aside/skills/aside-jev" 2>/dev/null || true
cp -R "$ROOT/skills/aside-jev" "$HOME/.agents/skills/aside-jev" 2>/dev/null || true
rsync -a --delete --exclude .venv --exclude .git "$ROOT/" "$DEST/" 2>/dev/null || cp -R "$ROOT"/. "$DEST/"

MARKER_BEGIN="# BEGIN aside-jev"
MARKER_END="# END aside-jev"
BLOCK=$(cat <<'MD'
# BEGIN aside-jev
## aside-jev (TypeSafe Jev × Aside)
When browser actions can be enumerated, use the `aside-jev` MCP (`jev_step` / `jev_choose`) so TypeSafe Jev selects only an application-owned candidate id, then execute that action via Aside. Never let the model invent selectors. Mock works without credentials; live needs `TYPESAFE_API_KEY`.
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
  if grep -q "$MARKER_BEGIN" "$AGENTS" 2>/dev/null; then
    # replace existing block
    python3 - "$AGENTS" <<'PY'
import pathlib,re,sys
path=pathlib.Path(sys.argv[1])
text=path.read_text()
block='''# BEGIN aside-jev
## aside-jev (TypeSafe Jev × Aside)
When browser actions can be enumerated, use the `aside-jev` MCP (`jev_step` / `jev_choose`) so TypeSafe Jev selects only an application-owned candidate id, then execute that action via Aside. Never let the model invent selectors. Mock works without credentials; live needs `TYPESAFE_API_KEY`.
# END aside-jev
'''
new=re.sub(r"# BEGIN aside-jev.*?# END aside-jev\n?", block, text, flags=re.S)
if new==text and "# BEGIN aside-jev" not in text:
    new=text.rstrip()+"\n\n"+block
path.write_text(new)
print("updated", path)
PY
  else
    printf '\n%s\n' "$BLOCK" >> "$AGENTS"
    echo "appended $AGENTS"
  fi
done

echo "aside-jev installed → $DEST"
command -v aside-jev && aside-jev --version || true
