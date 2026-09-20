#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv가 필요합니다. https://docs.astral.sh/uv/getting-started/installation/ 안내로 설치해 주세요." >&2
  exit 1
fi

# 패키지 설치는 지침 적용이나 브라우저 도우미 등록과 분리한다.
uv tool install --force --editable "$ROOT"
uv run --project "$ROOT" aside-jev --version
cat <<'TEXT'

Python 패키지 설치 완료. 확장 ON/OFF는 별도 설치 절차를 따릅니다.
1. Aside의 확장 관리에서 이 저장소의 extension 폴더를 로드합니다.
2. 팝업의 확장 ID와 적용할 Aside 계정 경로를 확인합니다.
3. scripts/setup_extension.py --help 와 docs/EXTENSION.md를 확인합니다.

홈 전체 AGENTS.md·권한·자동실행 항목은 변경하지 않았습니다.
TEXT
