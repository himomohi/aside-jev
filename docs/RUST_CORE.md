[English](RUST_CORE.md) | [한국어](RUST_CORE.ko.md)

# Rust performance core

This is the first stage of a Rust migration: UI observation ranking, reference
normalization, and pooled Jev System One HTTP transport run in Rust. Python still
owns CLI/MCP interfaces, credentials, sanitization, SDK schema validation, and
browser safety policy. Browser snapshot generation and Jev inference happen
outside this repository and are not accelerated by the local language change.

## Build from source

Install a Rust toolchain with Cargo, then run from the repository:

```bash
uv sync --frozen --extra dev --extra native
ASIDE_JEV_ENGINE=rust uv run --frozen --extra native aside-jev serve
```

PowerShell: set `$env:ASIDE_JEV_ENGINE = "rust"` before `uv run`.
`aside-jev-native` is built with maturin/PyO3 in release mode using the Python 3.11
stable ABI. The native extra currently supports source checkout builds; it is not
an independently published PyPI distribution. Existing installers keep the Python
path until native distribution is ready.

`ASIDE_JEV_ENGINE` is read once at startup. Restart MCP after changing it.

| Value | Behavior |
| :--- | :--- |
| `auto` (default) | Rust when installed, otherwise Python |
| `rust` | Require Rust; fail startup if missing |
| `python` | Use Python even when Rust is installed |

A Rust request error stops the request. It never resends through Python.
No decision results are cached.

## UI observations

Ordered score buckets replace sorting the entire tree. Equal-score document order,
32-line selection, the 4,800-character budget, and omission counts are preserved.
One host-Python casefold of the whole tree retains its exact Unicode behavior;
Rust ranking and reference normalization release the GIL. Sanitization still runs
before sending anything to Jev. Immutable observation identities normalize once.
Isolated JavaScript surrogates use the local Python string-processing path because
Rust strings cannot represent them; this never retries a provider request.

The REPL retains the **full** normalized snapshot identity in its existing task
session. Execution takes a **fresh** snapshot, compares its entire identity with
the retained identity, and requires exactly one matching target line. The expected
full tree is no longer embedded in each execution request. Python also requires
the supplied observation to be its last confirmed observation and invalidates
that cache before a call, preventing reuse after errors/cancellation. This removes
repeated outbound transfers while keeping the fresh snapshot and stale-page guard.

## System One transport

`reqwest` provides a shared HTTP pool through the SDK's public custom-transport
hook. Choice/Score/Noul serialization and response validation remain in the SDK.
The existing 8-request admission limit, 4-client/key pool, key rotation, idle
eviction, and deferred close remain in force. HTTP work releases the GIL. Retries
and redirects are disabled; errors are redacted and response bodies limited to 2 MB.

**Rust timeout semantics:** `timeout_s` is a total HTTP request deadline including
response-body reads (1–60 seconds). Python retains separate connect/read/write/pool
timeouts. The browser task's total deadline still applies. Native TLS uses platform
root certificates via rustls; Python-only HTTP transport settings are not translated.

## Reproduce and validate

```bash
cargo test --manifest-path rust/Cargo.toml --locked
cargo fmt --manifest-path rust/Cargo.toml --check
cargo clippy --manifest-path rust/Cargo.toml --locked --all-targets -- -D warnings
ASIDE_JEV_ENGINE=rust uv run --frozen --extra dev --extra native pytest -q
ASIDE_JEV_ENGINE=python uv run --frozen --extra dev --extra native pytest -q
uv run --frozen --extra native python scripts/benchmark_native.py --samples 100
```

The benchmark verifies equal results on a synthetic 10,002-line, 407,837-character
tree and identical SDK requests against a temporary localhost server. UI timings
include reference normalization and line selection after regex warmup. They exclude
redaction, snapshot generation, execution, and remote inference. HTTP timings
include each group's first connection. No API key or paid request is required.

Recorded 2026-10-05: macOS arm64, Python 3.12.13, rustc 1.95.0, release build.

| Local metric (100 samples) | Python | Rust |
| :--- | ---: | ---: |
| UI preprocessing p50 | 5.228 ms | 1.827 ms |
| UI preprocessing p95 | 5.518 ms | 1.865 ms |
| Pooled SDK transport p50 | 0.264 ms | 0.184 ms |
| Pooled SDK transport p95 | 0.330 ms | 0.237 ms |
| HTTP requests / TCP connections | 100 / 1 | 100 / 1 |

These measure local overhead, not end-to-end task speed. Live Jev inference and
real Aside snapshot generation have not been measured for this change. Regression
tests cover native/Python parity, real localhost HTTP, concurrent requests, no
retry/redirect, timeouts, redaction, and generated REPL stale/ambiguous-target guards.
CI runs native integration on Linux, macOS, and Windows.
