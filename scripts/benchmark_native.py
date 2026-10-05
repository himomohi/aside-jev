#!/usr/bin/env python3
"""Compare Python/Rust UI preprocessing and identical pooled SDK requests locally."""
from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import threading
from time import perf_counter

from typesafe_sdk import Choice, RetryPolicy, TypeSafeClient

from aside_jev.browser_flow import _compact_lines_python
from aside_jev.browser_runtime import REF
from aside_jev.native_core import http_transport, native
from benchmark_latency import LocalServer, measure


def timings(call, samples):
    call()  # warm compiled regexes and module initialization for both engines
    values = []
    for _ in range(samples):
        start = perf_counter()
        call()
        values.append((perf_counter() - start) * 1000)
    return {"p50_ms": round(statistics.median(values), 3),
            "p95_ms": round(sorted(values)[math.ceil(samples * .95) - 1], 3)}


def benchmark(samples):
    if native is None:
        raise RuntimeError("Run uv sync --extra native first; a Rust release build is required")
    tree = '\n'.join(f'- text "Unrelated item {i}" [ref=e{i}]' for i in range(10000))
    tree += '\n- link "Continue" [ref=f1e2]\n- heading "Journey complete"'
    names, terms = {"continue"}, {"journey", "complete", "continue"}
    def python_ui():
        return REF.sub("[ref]", tree), _compact_lines_python(tree, names, terms)
    def rust_ui():
        return native.normalize_refs(tree), native.compact_lines(tree, list(names), list(terms))
    assert python_ui() == rust_ui()
    ui = {"tree_chars": len(tree), "total_lines": 10002,
          "python": timings(python_ui, samples), "rust": timings(rust_ui, samples)}
    server = LocalServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    questions = {"aside_action": Choice(criteria={"inspect": "Inspect", "abstain": "Stop"})}
    transport = {}
    try:
        for engine, wire in (("python", None), ("rust", http_transport())):
            with TypeSafeClient(api_key="local-benchmark-only", base_url=f"http://127.0.0.1:{server.server_port}",
                                retry=RetryPolicy(max_retries=0), transport=wire) as client:
                def call():
                    answer = client.system_one(state={"goal": "Inspect page"}, questions=questions, model="jev-latest")
                    assert answer.choices["aside_action"].choice == "inspect"
                transport[engine] = measure(call, samples, server)
            assert transport[engine]["tcp_connections"] == 1
            assert transport[engine]["http_requests"] == samples
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
    return {"scope": "Synthetic UI preprocessing and localhost SDK transport; excludes browser snapshot creation and remote Jev inference.",
            "environment": {"python": platform.python_version(), "os": platform.system(), "architecture": platform.machine()},
            "samples": samples, "ui_preprocessing": ui, "pooled_transport": transport}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=100)
    args = parser.parse_args()
    if not 5 <= args.samples <= 1000:
        parser.error("samples must be 5..1000")
    print(json.dumps(benchmark(args.samples), indent=2))
