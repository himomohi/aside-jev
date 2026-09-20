#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ "$(uname -s)" != Darwin ]]; then
  echo "Use Install.cmd on Windows. This launcher supports macOS." >&2
  exit 1
fi
# uv와 Python은 앱 전용 폴더에 준비하며 PATH·로그인 항목을 수정하지 않는다.
INSTALL_ROOT="${ASIDE_JEV_INSTALL_DIR:-$HOME/Library/Application Support/AsideJev}"
if [[ -L "$INSTALL_ROOT" ]] || { [[ -e "$INSTALL_ROOT" ]] && { [[ ! -f "$INSTALL_ROOT/.installer-owned" ]] || [[ "$(cat "$INSTALL_ROOT/.installer-owned")" != 'aside-jev installer v1' ]]; }; }; then
  echo "Installation folder already exists without an ownership marker: $INSTALL_ROOT" >&2
  exit 1
fi
for path in "$INSTALL_ROOT" "$INSTALL_ROOT/bin" "$INSTALL_ROOT/bin/uv" "$INSTALL_ROOT/python" "$INSTALL_ROOT/cache" "$INSTALL_ROOT/runtime" "$INSTALL_ROOT/runtime/bin" "$INSTALL_ROOT/.installer-owned" "$INSTALL_ROOT/requirements.lock.txt"; do
  if [[ -L "$path" ]]; then echo "Linked installation path is not supported: $path" >&2; exit 1; fi
done
mkdir -p "$INSTALL_ROOT"
printf 'aside-jev installer v1\n' > "$INSTALL_ROOT/.installer-owned"
export UV_PYTHON_INSTALL_DIR="$INSTALL_ROOT/python"
export UV_PYTHON_BIN_DIR="$INSTALL_ROOT/bin"
export UV_CACHE_DIR="$INSTALL_ROOT/cache"
export UV_NO_MODIFY_PATH=1
UV="$(command -v uv || true)"
if [[ -z "$UV" && -x "$INSTALL_ROOT/bin/uv" ]]; then UV="$INSTALL_ROOT/bin/uv"; fi
if [[ -z "$UV" ]]; then
  case "$(uname -m)" in
    arm64) target=aarch64-apple-darwin; expected=85f00cbdc6dd3e97eba4c31b4d014375a9fdfe8f570023b84e5102fc3456896b ;;
    x86_64) target=x86_64-apple-darwin; expected=8dcf05a8c809bb3c471d2b614788ba27a6e41298fc8c31ac84b5f4339fd468e5 ;;
    *) echo "Unsupported architecture" >&2; exit 1 ;;
  esac
  download="$(mktemp -d)"
  trap 'rm -rf "$download"' EXIT
  echo "Preparing uv 0.12.17..."
  curl --fail --location --proto '=https' --tlsv1.2 "https://github.com/astral-sh/uv/releases/download/0.12.17/uv-$target.tar.gz" -o "$download/uv.tar.gz"
  actual="$(shasum -a 256 "$download/uv.tar.gz" | cut -d ' ' -f 1)"
  [[ "$actual" == "$expected" ]] || { echo "Download checksum failed" >&2; exit 1; }
  tar -xzf "$download/uv.tar.gz" -C "$download"
  mkdir -p "$INSTALL_ROOT/bin"
  cp "$download/uv-$target/uv" "$INSTALL_ROOT/bin/uv"
  UV="$INSTALL_ROOT/bin/uv"
fi
PYTHON="$INSTALL_ROOT/runtime/bin/python"
if [[ ! -f "$PYTHON" ]]; then
  "$UV" venv --python 3.11 "$INSTALL_ROOT/runtime"
fi
echo "Installing Aside Jev..."
"$UV" export --project "$ROOT" --frozen --no-dev --no-emit-project --format requirements-txt --output-file "$INSTALL_ROOT/requirements.lock.txt" > /dev/null
"$UV" pip install --python "$PYTHON" --require-hashes --requirements "$INSTALL_ROOT/requirements.lock.txt"
"$UV" pip install --python "$PYTHON" --no-deps --reinstall-package aside-jev "$ROOT"
"$PYTHON" -I -m aside_jev.cli setup "$@"
