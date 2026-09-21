[**English**](DEVELOPMENT.md) | [한국어](DEVELOPMENT.ko.md)

# Development checks

## Pull requests and main

Every pull request and push to `main` starts two independent workflows:

- **Quality checks:** Ruff correctness checks across Python files, basic Pyright checks for `core.py` and `browser_policy.py`, and the pure validation regression tests on Linux.
- **Platform installation verification:** the Python/JavaScript regression suites, translated-document checks, wheel build, and isolated installation/native-messaging checks on Windows and macOS.

A newer run cancels an older run for the same pull request or branch. The workflows use read-only repository permissions, do not persist checkout credentials, and never request a Jev API key. They do not use `pull_request_target` or run against a real Aside account. Manual execution remains available.

## Reproduce locally

```bash
uv sync --frozen --extra dev
uvx --from ruff==0.13.2 ruff check .
uvx --from pyright==1.1.407 pyright
uv run --frozen --extra dev pytest -q
node --test tests/test_extension_controller.mjs tests/test_ui_i18n.mjs tests/test_ui_flow.mjs tests/test_video_i18n.mjs
uv run --frozen python scripts/check_i18n.py
uv build --wheel
```

Ruff and Pyright run as isolated, version-pinned tools; they are not application runtime dependencies. Ruff initially gates syntax, undefined names, and related correctness issues without reformatting unrelated files. Pyright deliberately covers the pure validation boundary, not the entire application. Expand that scope together with fixes rather than suppressing diagnostics globally.

The full installer suite targets Windows/macOS. Linux CI only claims static and pure-validation coverage.

## Validation boundaries

[`browser_policy.py`](../src/aside_jev/browser_policy.py) owns action-rule and completion-condition validation. `ActionRule` remains importable from `browser_flow` for compatibility. Accessible names must not be blank; exact names and explicitly supplied fill values are preserved, including an empty value used to clear a field.

Completion text needs at least three characters after trimming whitespace, with at most 300 characters overall. The original text is still used for matching. An optional completion URL must have an HTTP(S) scheme, a host and valid port, and no whitespace/control characters; the original URL remains an exact-match condition. These checks are not a domain authorization policy or a general URL security scanner.

Candidate context limits include the automatically added `abstain` row. Parsing must not return a table that fails its own validation.

## What a green check does not establish

These workflows do not measure live Jev decision quality, inference latency, real-site task success, or real-account browser integration. Those need a separately authorized live evaluation. Do not interpret stub-backed tests as live end-to-end evidence. See the [existing validation record](VALIDATION.md).
