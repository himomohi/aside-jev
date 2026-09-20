[English](FEATURE_MAP.md) | **한국어**

# 기능 맵

| 기능 | 진입점 | 핵심 파일·심볼 | 데이터·외부 의존성 | 검증 |
| --- | --- | --- | --- | --- |
| 툴바 ON/OFF | MV3 action popup | extension/popup.js, controller.mjs | Native Messaging | node --test tests/test_extension_controller.mjs |
| 계정별 활성 상태·설정 | native-host, extension-status | extension_control.py, native_host.py | 명시한 Aside accountRoot, 키 파일, 로컬 설정 | test_extension_control.py, test_native_host.py |
| 간편 설치 | Install.command, Install.cmd, setup CLI | installer.py, scripts/install.sh | 고정 uv/Python, 패키지 확장, 기존 Aside 계정 | test_installer.py, macOS 초기 설치 |
| Native 등록 | setup CLI, scripts/setup_extension.py | extension_control.py, native_platform.py, native_registry.py | macOS manifest / 명시한 Windows HKCU 키 | test_extension_control.py, test_native_platform.py |
| REPL 브라우저 루프 | jev_browser_run MCP | browser_flow.py, browser_runtime.py | aside mcp의 repl, Jev | test_browser_flow.py, verify_browser_runtime.py |
| 결정·신뢰도·확장 OFF 게이트 | jev_choose, jev_step, jev_system_one | mcp_server.py, extension_gate.py | 확장 정책, typed Jev 응답 | test_mcp_server.py, test_jev.py |
| HTTP 연결 재사용 | choose_live, system_one | jev.py | typesafe-sdk, httpx2 | test_jev.py, benchmark_latency.py |
| 후보·관찰 제한 | parse_candidates, sanitize_context | core.py, aside_bridge.py | 앱 후보, 페이지 관찰 | test_core.py, test_observation.py |
| 로컬 결정 UI | dashboard CLI | dashboard.py, static/ | 127.0.0.1 HTTP, 세션 내 기록 | test_dashboard.py, CU 화면 확인 |
| 설치·설정 진단 | doctor CLI | cli.py | 키 존재 여부, Aside CLI | test_cli.py |
| 속도 비교 영상 | README GIF·MP4, `bun run render` | video/src/Root.tsx, scenes/, benchmark.json | Remotion 4.0.526, 로컬 전송 벤치마크 집계 | `cd video && bun run check`, 프레임·영상 메타데이터 확인 |

| 영어·한국어 UI | 대시보드·팝업 언어 메뉴 | static/i18n.mjs, extension/i18n.mjs, extension/_locales/ | 로컬 언어 선택, 추가 권한 없음 | test_ui_i18n.mjs, Computer Use |
| CLI 표시 언어 | --lang en 또는 ko | cli.py, cli_i18n.py | API 계약 유지 | test_cli_i18n.py |

확장 ON은 새 Aside 작업의 지침과 확장 전용 MCP에 적용됩니다. 기존 내장 도구를 전역 가로채는 경로는 구현되어 있지 않습니다.
