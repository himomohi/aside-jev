**English** | [한국어](VALIDATION.ko.md)

# Validation record

Date: 2026-09-20. Source preview 0.2.0. These checks were performed locally; publishing the source does not constitute a packaged release.

## Product checks

- Recorded Python regression suite: 146 tests before localization. Candidate contracts, confidence gates, HTTP reuse/concurrency, context preparation, dashboard server, Native Messaging, installation backup/recovery, and browser loop boundaries.
- Recorded JavaScript controller suite: 4 tests before localization. No ON indication before host confirmation, duplicate toggle prevention, uncertain failure state, settings/OFF changes.
- `uv build`: wheel and source distribution generated. Packaging does not prove extension installation or account connectivity.
- Shell/Python syntax, skill frontmatter, and Git whitespace checks.

Browser coverage includes six page transitions, page/action cycles, unchanged pages with different refs, stale observations, step/time budgets, exact completion URLs, OFF/confidence changes during decisions, invalid IDs/abstain/model errors, relevant content near the end of large pages, aggregate context preservation, and candidate-description collisions after sanitization. Aside initialization is included in the overall time budget.

## Actual Aside runtime

`scripts/verify_browser_runtime.py` opened a localhost fixture tab in a persistent REPL through actual `aside mcp`. It clicked links six times, refreshed observations each time, and verified completion text plus exact URL at the seventh choice. The test tab and HTTP server were closed afterward.

Recorded first run: 3,124.27ms, six executions, `verified`. **The decision function was a fixture stub; no actual Jev API call was made.** This does not establish Jev quality, inference latency, or general website success rates.

Native Messaging used temporary profiles and registration directories to exercise generated wrappers and length-prefixed JSON. Actual user Aside profiles and browser registration files were not changed.

<a id="latency"></a>

## Latency

`scripts/benchmark_latency.py --samples 30` connects the actual TypeSafe SDK to a localhost HTTP fixture without artificial delay.

| Strategy | p50 | p95 | TCP connections |
| --- | --- | --- | --- |
| New SDK client per request | 1.157ms | 1.695ms | 30 |
| Reuse client and connection | 0.540ms | 0.747ms | 1 |

Transport-path p50 overhead fell approximately 53.3% in this environment. Internet latency, TypeSafe server processing, and actual inference are excluded. `timeout_s` applies separately to HTTP phases; SDK automatic retries are zero.

The new-client group ran first, followed by reuse, with 30 requests each including the initial connection. There were no repeated trials, randomized ordering, or concurrent loads. Baseline calls the SDK directly, while reuse includes `choose_live` validation/context preparation, so client lifetime is not the only controlled variable. Per-request closing is included in baseline timing; final shared-client closing is outside the reuse interval. Raw samples were not retained; the video uses these aggregates.

## Speed duel video

[Source and reproduction](../video/README.md) · [English MP4](media/jev-speed-duel.mp4) · [English GIF](media/jev-speed-duel.gif) · [Korean MP4](media/jev-speed-duel.ko.mp4)

A 1920×1080, 30fps, 20-second data visualization. Both lanes use `elapsedMs = (frame - 60) / 150 × 1.157`, stopping at their respective p50. Baseline 1.157ms expands to five screen seconds; reuse finishes after approximately 2.334 seconds. It does not represent recorded browser work, the total time of 30 requests, or default Aside model versus Jev inference.

The original video passed TypeScript/ESLint, representative-frame review, H.264 decoding, and metadata checks (600 frames / 20 seconds). The GIF is 960×540, 240 frames, looping for 20 seconds. Computer Use verified the local README GIF and error-free MP4 playback through the end. Local links and loopback-only binding were checked. Remote GitHub rendering was not tested.

## UI evidence

Computer Use verified local demo decisions, results/probabilities/timing, invalid JSON, settings cancellation, and a 390px viewport. Without a key, Live selection is disabled. One observed demo round trip was 6.9ms; this is not a benchmark or Live latency measurement.

The popup HTML preview covered an unconfirmed host, disabled toggle, and reconnect guidance on localhost. Actual extension-context Native Messaging remains unverified.

[Original Korean UI evidence](screenshots/contact-sheet.jpg)

## English-default localization

- Full regression run after localization: **152 Python tests and 20 JavaScript tests passed**. Includes locale persistence/fallback, blocked storage, matching dictionaries/placeholders, HTML accessibility labels, real UI event flows, edited-input preservation, and stable native request contracts.
- TypeScript/ESLint passed. Both video locales decoded successfully as H.264, 1080p, 30fps, 600 frames / 20 seconds. Each GIF has 240 frames / 20 seconds. English/Korean frames were reviewed together.
- Computer Use confirmed fresh English UI, Korean switching, saved Korean after reload, translated result/status text, and preservation of a custom goal. Popup verification used localhost HTML with an unconnected host, not a real extension registration.
- Local English/Korean README previews displayed the matching GIF. Both language screenshots were refreshed from the actual demo UI. The English selector and labels fit a 390px viewport without horizontal overflow; the temporary viewport override was cleared afterward.
- Documentation artifact mappings and local links passed `scripts/check_i18n.py`. Wheel and source distribution rebuilt; packaged dashboard language modules were confirmed.
- CLI-owned messages default to English, with `--lang ko` for Korean. Original backend/provider diagnostics and generated agent instructions are outside the translated UI contract; see [localization boundaries](I18N.md).

![English and Korean UI evidence](screenshots/i18n-contact-sheet.jpg)

## Remaining boundaries

- Actual Jev API authentication, decision quality, and inference time remain unverified.
- Real-account extension installation, Native Messaging registration, and MCP configuration remain unverified.
- ON affects new-task instructions and the provided MCP; no native hook globally intercepts existing direct tools.
- Task-specific action rules and completion conditions are required. General browser-agent capability is not established.
- OFF/timeout does not undo actions already sent. Inspect `unconfirmed` state before manually resuming.
- Sanitization is an auxiliary size/credential-pattern filter, not universal personal-data detection.
- These local checks do not establish remote CI results or a published GitHub release.
