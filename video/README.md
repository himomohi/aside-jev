**English** | [한국어](README.ko.md)

# Jev speed duel

[English MP4](../docs/media/jev-speed-duel.mp4) · [GIF](../docs/media/jev-speed-duel.gif) · [Still](../docs/media/jev-speed-duel-poster.png) · [한국어 영상](../docs/media/jev-speed-duel.ko.mp4)

A silent 20-second Remotion video at 1920×1080 and 30fps. Deep green, ivory, and lime carry three scenes: setup → simultaneous race → results.

## What it compares

**The same Jev SDK with a new client per request versus client and connection reuse.** This is not a default Aside model versus Jev task-speed comparison. Model inference and internet round trips are excluded.

| 2026-09-20 · 30 requests per method | New client | Reused connection |
| --- | ---: | ---: |
| p50 | 1.157ms | 0.540ms |
| p95 | 1.695ms | 0.747ms |
| TCP connections | 30 | 1 |

Source: [benchmark_latency.py](../scripts/benchmark_latency.py). Recorded aggregates and limitations: [validation](../docs/VALIDATION.md#latency). Both languages read [benchmark.json](src/benchmark.json), with the 53.3% reduction calculated from p50. Update that JSON and the validation record together before rendering new measurements; results vary by environment.

Raw per-request samples were not retained. No claims are made about statistical significance or individual samples. This was one sequential run including the first connection. The baseline calls the SDK directly; reuse includes app validation/context preparation. Client-close timing also differs. See the validation record for details.

## Localization

English is the default. Text lives in [`src/locales/en.json`](src/locales/en.json) and [`src/locales/ko.json`](src/locales/ko.json). `LocaleContext` supplies one dictionary to the shared scenes. Unsupported composition locales fall back to English; the CLI rejects unsupported locale arguments. TypeScript checks dictionary shape, while the localization check enforces exact key parity.

| Locale | Composition input | Media base name |
| --- | --- | --- |
| English (default) | `{"locale":"en"}` | `jev-speed-duel` |
| Korean | `{"locale":"ko"}` | `jev-speed-duel.ko` |

## Render

Requires Bun, Node.js 22+, and FFmpeg. Remotion 4.0.526 is pinned. The first render downloads Chrome Headless Shell.

```bash
cd video
bun install --frozen-lockfile
bun run check
bun run stills --locale all
bun run render --locale all
bun run gif --locale all
```

Omit `--locale` for English only, or use `--locale ko` for Korean only. `stills` writes representative PNG frames to ignored `out/`. `render` writes H.264 MP4 and a poster PNG to `docs/media/`. `gif` converts MP4 to a looping 960×540, 12fps preview. The animation, measurements, and timing are shared across languages.

The font stack is Arial → Apple SD Gothic Neo → Noto Sans KR → system sans-serif. These assets were rendered on macOS. Install a Korean font on other systems; font differences can affect wrapping.

The one-shot renderer uses `scripts/loopback-only.cjs` to bind temporary TCP servers to **127.0.0.1 only**. It does not register Studio, watchers, login items, or public servers. Browser and render servers are closed when rendering finishes. Use the wrapper commands above.

## Timing

- 0–4s: comparison setup.
- Approximately 4–13.6s: countdown, simultaneous start, held result.
- Approximately 13.2–20s: scorecard. Scenes crossfade for 0.4s.
- From race-local frame 60: `elapsedMs = (frame - 60) / 150 × 1.157`.
- Baseline: 150 frames / 5 seconds. Reuse: approximately 70.01 frames / 2.334 seconds, quantized to rendered frames.
- Each timer stops at its p50. Both lanes use the same time conversion.

This expands single-request p50 values. It is not browser footage or the total time of 30 requests.

## Source map

| File | Responsibility |
| --- | --- |
| `src/Root.tsx` | 600-frame composition, locale input, transitions |
| `src/i18n.ts`, `src/locales/` | English default, typed dictionaries, Korean translation |
| `src/theme.tsx` | Colors, typography, persistent scope note |
| `src/scenes/` | Setup, race, results |
| `src/benchmark.json` | Aggregates and measurement provenance |
| `scripts/render.mjs` | Bundle, stills, MP4, locale selection |
| `scripts/gif.mjs` | Localized README GIF generation |

Uses the [Remotion rendering API](https://www.remotion.dev/docs/renderer/render-media). The README includes GIF and MP4 links, plus a still image for a motion-free alternative.
