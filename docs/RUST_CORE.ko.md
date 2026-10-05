[English](RUST_CORE.md) | [한국어](RUST_CORE.ko.md)

# Rust 성능 코어

Rust 전환의 첫 단계로 UI 관찰의 관련 줄 선택·참조 정규화와 Jev System One의
HTTP 연결 풀을 Rust로 옮겼습니다. CLI·MCP 인터페이스·자격증명 접근·문맥 가림·
SDK 검증·브라우저 안전 정책은 Python을 유지합니다. 브라우저 스냅샷 생성과
원격 Jev 추론은 이 저장소 밖에서 수행되므로 언어 변경만으로 빨라지지 않습니다.

## 소스에서 빌드

Cargo가 포함된 Rust 도구 체인을 설치하고 저장소에서 실행합니다.

```bash
uv sync --frozen --extra dev --extra native
ASIDE_JEV_ENGINE=rust uv run --frozen --extra native aside-jev serve
```

PowerShell에서는 먼저 `$env:ASIDE_JEV_ENGINE = "rust"`를 설정합니다.
별도 패키지 `aside-jev-native`는 maturin/PyO3로 release 빌드되며 Python 3.11
stable ABI를 사용합니다. native extra는 현재 소스 체크아웃에서 빌드하는 용도이며
독립적으로 PyPI에 배포되지 않았습니다. 기존 설치기는 Python 경로를 사용합니다.

환경 변수 `ASIDE_JEV_ENGINE`은 시작 시 한 번 읽습니다. 변경 후 MCP를 재시작합니다.

| 값 | 동작 |
| :--- | :--- |
| `auto` (기본값) | Rust가 설치되면 Rust, 없으면 Python |
| `rust` | Rust 필수, 없으면 시작 실패 |
| `python` | Rust 설치 여부와 관계없이 Python 사용 |

Rust 요청 실패 시 중단하며 Python으로 재전송하지 않습니다. 결정은 캐시하지 않습니다.

## UI 관찰

전체 트리를 정렬하는 대신 점수별 버킷에서 관련 줄을 선택합니다. 같은 점수의
문서 순서, 32줄·4,800자 한도, 생략 줄 수를 유지합니다. 전체 트리를 호스트
Python으로 한 번 casefold하여 Unicode 버전별 동작을 유지합니다. Rust 선택·
정규화 작업은 GIL을 해제하고, Jev 전송 전에는 기존 가림 처리를 적용합니다.
불변 Python 관찰의 전체 상태 정규화는 한 번만 수행합니다.
Rust 문자열로 표현할 수 없는 단독 JavaScript surrogate는 로컬 Python 문자열
처리 경로로 처리하며, 제공자 요청을 재시도하지 않습니다.

REPL 세션에 직전 스냅샷의 **전체** 정규화 상태를 보관합니다. 실행 직전에는
**새** 스냅샷의 전체 상태를 비교하고 정확히 하나의 행동 대상만 허용합니다.
실행 요청에 기존 전체 트리를 다시 넣지 않아 반복 전송을 줄입니다. Python도
마지막으로 확인한 관찰만 허용하고 호출 전에 캐시를 무효화하므로 취소·오류 후
이전 관찰을 재사용할 수 없습니다. 새 스냅샷과 오래된 화면 검증은 유지합니다.

## System One 요청

SDK의 공개 custom transport 훅에 `reqwest` 연결 풀을 연결합니다. Choice·Score·
Noul 직렬화와 응답 검증은 SDK가 담당합니다. 기존 동시 요청 8개 제한, 키별
클라이언트 4개 풀, 키 교체, 유휴 연결 제거, 요청 종료 후 정리를 유지합니다.
HTTP 작업은 GIL을 해제합니다. 재시도·리디렉션은 비활성화하고 오류 내용을
가리며 응답 본문은 2 MB로 제한합니다.

**Rust의 `timeout_s`는 본문 읽기를 포함한 HTTP 요청 전체 제한입니다 (1–60초).**
Python 경로의 connect/read/write/pool 개별 제한과 차이가 있습니다. 브라우저
작업 전체 제한도 유지합니다. Rust TLS는 rustls와 시스템 인증서를 사용하며
Python 전용 HTTP 전송 설정을 자동으로 변환하지 않습니다.

## 검증과 재현

```bash
cargo test --manifest-path rust/Cargo.toml --locked
cargo fmt --manifest-path rust/Cargo.toml --check
cargo clippy --manifest-path rust/Cargo.toml --locked --all-targets -- -D warnings
ASIDE_JEV_ENGINE=rust uv run --frozen --extra dev --extra native pytest -q
ASIDE_JEV_ENGINE=python uv run --frozen --extra dev --extra native pytest -q
uv run --frozen --extra native python scripts/benchmark_native.py --samples 100
```

합성 UI 트리 10,002줄·407,837자와 임시 localhost 서버로 Python/Rust 결과가
같은지 확인합니다. 양쪽 모두 동일한 SDK 요청 100회와 TCP 연결 1개로 측정합니다.
UI 측정은 정규식 준비 후의 참조 정규화·줄 선택을 포함하고 가림·스냅샷 생성·
행동 실행·원격 추론은 제외합니다. HTTP에는 각 엔진의 첫 연결이 포함됩니다.
API 키나 유료 요청은 필요하지 않습니다.

2026-10-05: macOS arm64, Python 3.12.13, rustc 1.95.0, release 빌드.

| 로컬 측정 (100회) | Python | Rust |
| :--- | ---: | ---: |
| UI 전처리 p50 | 5.228 ms | 1.827 ms |
| UI 전처리 p95 | 5.518 ms | 1.865 ms |
| 연결 재사용 SDK 전송 p50 | 0.264 ms | 0.184 ms |
| 연결 재사용 SDK 전송 p95 | 0.330 ms | 0.237 ms |
| HTTP 요청 / TCP 연결 | 100 / 1 | 100 / 1 |

로컬 오버헤드 결과이며 전체 작업 속도 향상을 의미하지 않습니다. 실제 Jev 추론과
Aside 스냅샷 생성 지연은 측정하지 않았습니다. Python/Rust 결과 비교, localhost
HTTP, 동시 요청, 재시도·리디렉션 차단, 제한 시간, 가림 처리, 생성한 REPL 코드의
오래된 화면·중복 대상 차단을 회귀 테스트로 검증합니다. CI에 Linux·macOS·Windows
native 통합 검사를 추가했습니다.
