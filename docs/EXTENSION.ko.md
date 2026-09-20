[English](EXTENSION.md) | **한국어**

# Aside 툴바 확장 연결

이 패키지는 MV3 팝업, 요청 시 실행되는 Native Messaging 도우미, 지속 MCP 프로세스로 구성됩니다. 확장에는 `nativeMessaging` 권한만 있으며 백그라운드 service worker·content script·전체 사이트 권한이 없습니다. 운영체제 서비스·로그인 항목을 만들지 않습니다.

## 연결 순서

1. `uv sync`로 현재 프로젝트의 Python 환경을 준비합니다.
2. Aside의 확장 관리 화면에서 개발자 모드를 사용해 이 저장소의 `extension/` 폴더를 압축 해제된 확장으로 로드합니다. 폴더를 옮기면 확장 ID가 달라질 수 있습니다.
3. 확장 ID, 대상 Aside `accountRoot`, 해당 Aside 빌드의 Native Messaging 등록 폴더를 확인합니다. 설치기는 계정이나 호스트 경로를 추측하지 않습니다.
4. 아래 미리보기 명령에서 실제 값을 사용합니다.

```bash
uv run python scripts/setup_extension.py \
  --extension-id '확장 관리 화면의 32자리 ID' \
  --profile-dir '/절대/Aside/accountRoot' \
  --native-host-dir '/절대/Aside/NativeMessagingHosts' \
  --env-file '/절대/키환경파일' \
  --profile-label '내 Aside 계정' \
  --dry-run
```

미리보기의 대상 경로를 확인하고 같은 명령의 `--dry-run`을 `--apply`로 바꾸면 연결 파일이 등록됩니다. 기존 파일은 백업됩니다. Native Messaging 등록은 프로그램 실행 연결을 추가하는 작업이므로 설치를 수행하는 환경의 사용자 승인 정책을 따르세요.

키 파일은 `TYPESAFE_API_KEY` 또는 `TYPESAFEAI_API_KEY`의 단순 할당만 허용합니다. 파일을 shell로 source하지 않으며 임의 명령은 실행하지 않습니다. 키 원문은 팝업과 상태 응답에 노출하지 않습니다.

5. 팝업의 **MCP 설정 복사**, 또는 `uv run aside-jev extension-status` 결과의 `mcp_config` / `aside_mcp_entry`로 Aside 설정의 MCP 연결을 등록합니다. 전용 wrapper는 `serve --extension`으로 실행되어 ON/OFF를 매 요청에 반영합니다. 별도 `--config-dir`로 설치했다면 상태 조회에도 같은 `ASIDE_JEV_CONFIG_DIR`을 지정합니다.
6. 팝업의 연결을 새로 확인하고 ON을 선택합니다. 키 존재와 지침 저장을 확인한 뒤 ON으로 표시합니다. 키가 존재한다는 사실은 실제 API 인증 성공을 뜻하지 않습니다.
7. **새 Aside 작업**에서 브라우저 작업을 시작합니다. 연속 작업은 `jev_browser_run`으로 전달합니다.

## ON/OFF 의미

- ON: 선택한 accountRoot의 AGENTS.md 관리 구간과 `skills/user/aside-jev/SKILL.md`를 적용합니다. 각 실행 경계에서 활성 상태를 재확인합니다.
- OFF: 해당 AGENTS.md 관리 구간을 해제합니다. 상태 확인용 스킬 파일은 유지되며 OFF에서 확장 경로를 사용하지 않도록 안내합니다. 확장 전용 MCP는 새 결정을 거부합니다. 이미 시작한 네트워크/브라우저 동작을 되돌리지는 않습니다.
- 기존 홈·Aside 전역 지침에 옛 `aside-jev` 규칙이 있으면 경고합니다. 이 확장은 전역 파일을 자동 수정하지 않습니다.
- 연결이 끊기거나 저장에 실패하면 기존 ON 표시를 유지하지 않고 **상태 확인 필요**로 표시합니다.
- 모든 내장 도구를 가로채는 훅은 없습니다. Jev 실행을 엄격히 확인할 수 있는 범위는 제공한 MCP 경로입니다.

## 비활성화와 제거

먼저 팝업에서 OFF로 바꾸고 새 작업을 사용하세요. 완전히 제거하려면 Aside MCP 설정에서 해당 연결을 비활성화하고 확장을 제거합니다. 설치 미리보기에 표시된 Native Messaging manifest와 설정 폴더의 wrapper는 보관하거나 제거할 수 있습니다. 기존 계정 문서는 백업에서 복구할 수 있습니다. 다른 도구의 파일이나 전역 AGENTS.md는 제거 대상이 아닙니다.

## 설치 검증의 현재 범위

임시 계정 폴더에서 native host framing, origin 검증, ON/OFF, 백업·실패 복구, 생성된 wrapper 실행을 검증했습니다. 실제 사용자 Aside 계정에 확장을 로드하고 Native Messaging을 등록하는 단계는 이 코드 변경의 검증에 포함하지 않았습니다. 브라우저별 등록 경로와 UI 연결은 설치할 환경에서 확인해야 합니다.
