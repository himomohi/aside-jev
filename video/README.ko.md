[English](README.md) | **한국어**

# Jev 속도 대결 영상

[20초 MP4](../docs/media/jev-speed-duel.ko.mp4) · [README GIF](../docs/media/jev-speed-duel.ko.gif) · [정지 화면](../docs/media/jev-speed-duel.ko-poster.png)

Remotion으로 만든 1920×1080 · 30fps · 20초 무음 영상입니다. 아이보리와 라임을 깊은 녹색 배경에 배치하고, 소개 → 동시 출발 레이스 → 결과 점수판으로 구성합니다.

영어가 기본 언어입니다. `src/locales/en.json`과 `ko.json` 사전을 같은 장면에 적용합니다. `--locale en`, `--locale ko`, `--locale all`로 출력 언어를 선택하고, 생략하면 영어입니다. 한국어 파일은 `.ko` 접미사를 사용합니다. 측정 데이터와 타이밍은 공유합니다.

## 무엇을 비교하나요?

**동일 Jev SDK의 요청마다 클라이언트 생성 vs 클라이언트·연결 재사용**을 비교합니다. 실제 Aside 기본 모델 vs Jev의 작업 속도 영상은 아닙니다. 모델 추론과 인터넷 왕복은 측정하지 않았습니다.

| 2026-09-20 · 각 방식 30회 | 요청마다 생성 | 재사용 |
| --- | ---: | ---: |
| p50 | 1.157ms | 0.540ms |
| p95 | 1.695ms | 0.747ms |
| TCP 연결 | 30 | 1 |

측정 출처는 [benchmark_latency.py](../scripts/benchmark_latency.py), 보존된 집계는 [검증 기록](../docs/VALIDATION.md#레이턴시)입니다. 영상 데이터는 [benchmark.json](src/benchmark.json) 하나에서 읽고, 감소율 53.3%는 p50 값으로 계산합니다. 새 측정값을 반영할 때는 이 JSON과 검증 기록을 함께 갱신하고 다시 렌더링하세요. 실행마다 수치는 달라질 수 있습니다.

원시 표본은 없으므로 샘플별 시간·통계적 유의성을 주장하지 않습니다. 순차 단일 실행이며 첫 연결을 포함합니다. 기본 경로는 SDK 직접 호출, 재사용 경로는 앱 검증·문맥 정제를 포함합니다. 클라이언트 종료 비용의 측정 범위도 다릅니다. 상세 조건은 검증 기록을 참조하세요.

## 시간 표현

- 0–4초: 동일 Jev SDK라는 비교 조건과 두 방식 소개
- 약 4–13.6초: 카운트다운, 동시 출발, 결과 유지
- 약 13.2–20초: 결과 점수판. 장면 전환은 0.4초 교차
- 레이스 내부 프레임 60부터 `elapsedMs = (frame - 60) / 150 × 1.157`
- 기준 레인은 150프레임(5초), 재사용은 약 70.01프레임(2.334초)에 해당. 실제 표시는 프레임 단위로 반올림됩니다.
- 각 타이머는 해당 p50에서 멈춥니다. 두 레인에 같은 시간 배율을 적용했습니다.

이는 단일 요청 p50의 확대 시각화입니다. 실제 브라우저 화면 녹화나 30개 요청의 합계 시간이 아닙니다. 별도 배속을 줘서 한쪽을 빠르게 보이게 하지 않습니다.

## 다시 만들기

Bun, Node.js 22+, FFmpeg가 필요합니다. 렌더링 도중 Remotion이 Chrome Headless Shell을 처음 한 번 내려받습니다. Remotion 버전은 4.0.526으로 고정했습니다.

```bash
cd video
bun install --frozen-lockfile
bun run check
bun run stills --locale ko
bun run render --locale ko
bun run gif --locale ko
```

- `stills`: 대표 프레임을 `out/`에 출력합니다(버전 관리 제외).
- `render`: `docs/media/`에 H.264 MP4와 PNG 정지 화면을 출력합니다.
- `gif`: MP4에서 960×540 · 12fps · 반복 GIF를 생성합니다.
- 폰트는 Arial → Apple SD Gothic Neo → Noto Sans KR → 시스템 sans-serif 순입니다. 이 산출물은 macOS에서 렌더링했으며 다른 OS에서는 한국어 폰트를 설치해야 합니다. 글꼴 차이로 줄바꿈이 바뀔 수 있습니다.

`scripts/loopback-only.cjs`는 렌더 프로세스의 임시 TCP 서버를 127.0.0.1에만 바인딩합니다. 시작·종료가 있는 일회성 렌더링이며 Studio, watcher, 로그인 실행, 외부 공개 서버를 등록하지 않습니다. 종료 시 브라우저와 임시 렌더 서버를 정리합니다. 재현 시 위 래퍼를 사용하세요.

## 파일 구조

| 파일 | 역할 |
| --- | --- |
| `src/Root.tsx` | 600프레임 구성, 장면 전환 |
| `src/theme.tsx` | 공통 색상·서체·비교 범위 표시 |
| `src/scenes/` | 소개, 레이스, 점수판 |
| `src/benchmark.json` | 측정값·출처·추론 미포함 상태 |
| `scripts/render.mjs` | 번들·프레임·MP4 렌더링 |
| `scripts/gif.mjs` | README용 GIF 생성 |

[Remotion 렌더링 API](https://www.remotion.dev/docs/renderer/render-media)를 사용합니다. README는 GIF와 MP4 링크를 함께 제공하고, 자동 재생을 원치 않을 때 볼 수 있는 PNG도 제공합니다.
