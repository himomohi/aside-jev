**English** | [한국어](CHANGELOG.ko.md)

# Changelog

## 0.2.0 — Unreleased

- `jev_browser_run`: persistent Aside REPL observation → compact context → Jev selection → execution → fresh observation. Stops on cycles, stale observations, no progress, and step/time budgets.
- MV3 toolbar popup and Native Messaging helper: ON/OFF, account-scoped instructions, key readiness, and decision thresholds.
- Extension-specific MCP: rejects requests while OFF, requires Live decisions, and enforces the configured confidence threshold. Does not intercept all built-in Aside tools.
- SDK HTTP connection reuse, asynchronous MCP request processing, no automatic retries, and explicit timeout/context limits.
- Reject duplicate candidates, invalid providers, malformed confidence, and low-confidence execution.
- Local decision workspace, timing breakdown, session records, CLI diagnostics, and a localhost SDK benchmark.
- Remove installation-time edits to home-wide instructions. Use explicit installation and account-scoped backups.
- English by default with Korean UI localization, paired READMEs, and localized Remotion videos sharing measurements and timing.
