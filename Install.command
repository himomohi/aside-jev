#!/bin/bash
# Finder에서 실행한 창을 유지해 성공·실패 안내를 읽을 수 있게 한다.
ROOT="$(cd "$(dirname "$0")" && pwd)"
bash "$ROOT/scripts/install.sh" "$@"
result=$?
if [ -t 0 ]; then read -r -p "Press Enter to close / Enter로 닫기"; fi
exit "$result"
