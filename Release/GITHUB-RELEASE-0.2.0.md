# Aside Jev 0.2.0

Aside observes and executes; Jev selects from app-owned candidates.

## Changes

- Compact icon popover with connection animation, accessible controls, reduced-motion support, and expandable settings/diagnostics.
- ON checks the local MCP launcher, live Jev authentication, and the current Aside connection before extension MCP execution is allowed. OFF, changed settings/keys, or one-hour expiry require a new check.
- Dedicated masked API-key entry on macOS, backed by Keychain; saved secrets are never returned to the extension.
- Automatic English/Korean tooltips based on country lookup, browser-language fallback, and manual override. IP addresses are not stored.
- Bounded browser decisions, fresh observations, confidence thresholds, and integrated completion/risk assessment. Failures stop execution without silently switching models.
- Guided Windows/macOS installers, localized documentation, persistent REPL integration, and reproducible localhost SDK transport benchmarks.

## Install

Download `aside-jev-source.zip`, extract it, and follow `README.md` / `README.ko.md`. The archive includes `Install.command`, `Install.cmd`, source, extension assets, and the MIT license. A Python wheel and source distribution are also provided; SHA-256 hashes are in `SHA256SUMS`.

This is source/script distribution, not a signed/notarized macOS application or a store-signed browser extension. It requires Aside, Python 3.11+ (the guided installer can prepare it), and your own TypeSafe credentials for live use. The extension does not globally intercept built-in Aside tools. Existing tasks are not automatically switched. Windows CI checks isolated installation/native messaging; real Windows browser integration has not been verified.

## Validation

Local Python and JavaScript regressions, Ruff/Pyright, translation/link checks, package inspection, and isolated macOS installation are release gates. Installed macOS Aside popup OFF→verified ON, Keychain UI, and a synthetic live browser completion were checked during development. These checks do not establish success on arbitrary sites or benchmark actual model inference.

## Links

- [Repository](https://github.com/himomohi/aside-jev)
- [Version release](https://github.com/himomohi/aside-jev/releases/tag/v0.2.0)
- [Download source and installers](https://github.com/himomohi/aside-jev/releases/latest/download/aside-jev-source.zip)

## 한국어

아이콘 팝오버, ON 연결 검증, macOS 키체인 입력 창, IP 기반 한·영 툴팁, 브라우저 완료·위험 평가를 포함한 첫 릴리즈입니다. 소스 ZIP을 풀고 `README.ko.md`를 따라 설치하세요. 서명·공증된 앱 배포가 아니며 Aside 내장 도구 전체 가로채기는 지원하지 않습니다. Windows 실제 브라우저 연동은 미확인입니다.
