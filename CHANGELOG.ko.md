[English](CHANGELOG.md) | **한국어**

# 변경 기록

## 0.2.0 — 2026-09-21

- 상태 애니메이션·접근성 컨트롤·펼침 진단을 제공하는 아이콘 팝오버.
- ON에서 로컬 MCP·실제 API·Aside 준비 검증 후 실행 허용. 키·설정 변경과 만료 시 재검증.
- macOS 키체인 숨김 입력 창 및 IP 기반 한·영 확장 번역.
- 브라우저 완료·위험 평가 통합과 수동 MCP 복구.
- `jev_browser_run`: 지속 Aside REPL의 관찰 → 문맥 정제 → Jev 선택 → 실행 → 새 관찰 루프. 반복·오래된 관찰·무진행·단계/시간 예산에서 중단.
- Aside 툴바용 Manifest V3 팝업과 Native Messaging 도우미: ON/OFF, 계정별 지침 적용, 키 준비 상태, 판단 기준 설정.
- 확장 전용 MCP: OFF 요청 거부, Live 전용 결정, 설정된 최소 신뢰도 적용. 기존 Aside 직접 도구 전체를 가로채는 기능은 미지원.
- SDK HTTP 연결 재사용, MCP의 비동기 요청 처리, 자동 재시도 제거, HTTP timeout과 문맥 크기 제한.
- 중복 후보·잘못된 provider·비정상 신뢰도 거부, 저신뢰도 실행 차단.
- 로컬 결정 작업 공간, 구간별 소요 시간, 세션 기록, CLI doctor, localhost SDK 벤치마크.
- 기존 설치 스크립트의 홈 전체 지침 수정을 제거. 별도 명시 설치와 계정별 백업을 사용.
- 영어 기본 UI와 한국어 i18n, 언어별 README, 같은 측정값·타이밍을 공유하는 영문·한글 Remotion 영상.
- Windows/macOS 간편 설치 파일에서 Python/uv 준비, 고정 ID 확장 복사, 계정 MCP 설정 병합·백업을 처리합니다. Windows 메시지·파일 잠금·명시적 HKCU 등록을 추가했으며 Windows 실기기 브라우저 연결은 미검증입니다.
