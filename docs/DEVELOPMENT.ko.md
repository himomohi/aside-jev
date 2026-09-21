[English](DEVELOPMENT.md) | [**한국어**](DEVELOPMENT.ko.md)

# 개발 검증

## PR과 main 자동 검사

모든 PR과 `main` 푸시에서 두 워크플로가 독립적으로 실행됩니다.

- **Quality checks:** Linux에서 Python 파일의 Ruff 오류 검사, `core.py`·`browser_policy.py`의 Pyright 기본 타입 검사, 순수 입력 검증 회귀 테스트를 실행합니다.
- **Platform installation verification:** Windows·macOS에서 Python·JavaScript 회귀 테스트, 번역 문서 검사, wheel 빌드, 격리된 설치·Native Messaging 검증을 실행합니다.

같은 PR이나 브랜치에 새 실행이 생기면 이전 실행을 취소합니다. 저장소 권한은 읽기 전용이며 체크아웃 인증정보를 남기지 않습니다. Jev API 키를 요청하거나 실제 Aside 계정으로 실행하지 않고, `pull_request_target`도 사용하지 않습니다. 수동 실행은 유지합니다.

## 로컬에서 재현하기

```bash
uv sync --frozen --extra dev
uvx --from ruff==0.13.2 ruff check .
uvx --from pyright==1.1.407 pyright
uv run --frozen --extra dev pytest -q
node --test tests/test_extension_controller.mjs tests/test_ui_i18n.mjs tests/test_ui_flow.mjs tests/test_video_i18n.mjs
uv run --frozen python scripts/check_i18n.py
uv build --wheel
```

Ruff·Pyright는 버전을 고정한 격리 도구로 실행하며 앱 실행 의존성에는 추가하지 않습니다. Ruff는 우선 문법, 정의되지 않은 이름 등 실제 오류 위주로 검사하고 관련 없는 파일의 포맷은 변경하지 않습니다. Pyright 적용 범위는 앱 전체가 아닌 순수 입력 검증 모듈입니다. 진단을 전역으로 숨기는 대신 실제 수정과 함께 적용 범위를 넓힙니다.

전체 설치 검증 대상은 Windows·macOS입니다. Linux CI는 정적 검사와 순수 입력 검증 테스트만 확인합니다.

## 입력 검증 범위

[`browser_policy.py`](../src/aside_jev/browser_policy.py)가 행동 규칙과 완료 조건을 검증합니다. 기존 코드의 호환성을 위해 `browser_flow`에서도 `ActionRule`을 가져올 수 있습니다. 접근성 이름은 공백만으로 구성할 수 없으며, 입력한 정확한 이름과 명시적인 fill 값은 그대로 보존합니다. 입력칸을 지우기 위한 빈 문자열도 허용합니다.

완료 문구는 앞뒤 공백을 제외하고 최소 3자, 전체 길이는 최대 300자여야 합니다. 실제 비교에는 원문을 그대로 사용합니다. 선택적인 완료 URL은 HTTP(S) 스킴, 호스트, 유효한 포트를 갖춰야 하며 공백·제어문자를 허용하지 않습니다. URL의 정확한 일치 조건은 유지합니다. 이 검사는 도메인 접근 권한 정책이나 범용 URL 보안 검사기가 아닙니다.

후보 목록의 컨텍스트 길이 제한에는 자동 추가되는 `abstain`도 포함됩니다. 파서는 자체 검증을 통과하지 못하는 후보 목록을 반환하지 않아야 합니다.

## CI 통과가 입증하지 않는 것

실제 Jev의 판단 품질·추론 지연·외부 사이트 작업 성공률·실제 계정 브라우저 연동은 이 워크플로에서 측정하지 않습니다. 별도로 승인된 실서비스 평가가 필요합니다. 스텁 기반 테스트를 실제 E2E 검증으로 해석하지 마세요. [기존 검증 기록](VALIDATION.ko.md)을 참고하세요.
