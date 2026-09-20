#!/usr/bin/env python3
"""실제 SDK와 localhost HTTP로 연결 재사용 비용을 측정한다. 원격 Jev 지연 측정은 아니다."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
import socket
import statistics
import threading
from time import perf_counter
from typing import Callable

from typesafe_sdk import Choice, RetryPolicy, TypeSafeClient

from aside_jev import jev
from aside_jev.core import Candidate


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.connection_count = 0
        self.request_count = 0

    def get_request(self):
        connection, address = super().get_request()
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.connection_count += 1
        return connection, address


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.server.request_count += 1
        payload = json.dumps({
            "model": "local-benchmark", "usage": {"input_tokens": 10, "output_tokens": 1},
            "answers": {"aside_action": {"type": "choice", "choice": "inspect", "confidence": 0.9, "probabilities": {"inspect": 0.9, "abstain": 0.1}}},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        self.wfile.flush()

    def log_message(self, *_args):
        pass


def measure(call: Callable[[], None], samples: int, server: LocalServer) -> dict:
    before_connections, before_requests = server.connection_count, server.request_count
    timings = []
    for _ in range(samples):
        started = perf_counter()
        call()
        timings.append((perf_counter() - started) * 1000)
    ordered = sorted(timings)
    return {
        "samples": samples,
        "p50_ms": round(statistics.median(timings), 3),
        "p95_ms": round(ordered[math.ceil(samples * 0.95) - 1], 3),
        "min_ms": round(min(timings), 3),
        "http_requests": server.request_count - before_requests,
        "tcp_connections": server.connection_count - before_connections,
    }


def benchmark(samples: int = 30) -> dict:
    server = LocalServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}/v1"
    previous_base_url = os.environ.get("TYPESAFE_BASE_URL")
    os.environ["TYPESAFE_BASE_URL"] = base_url
    jev.close_clients()
    candidates = [Candidate("inspect", "Inspect the current page", tool="snapshot"), Candidate("abstain", "No safe action")]
    questions = {"aside_action": Choice(instructions="Choose the next supplied action", criteria={candidate.id: candidate.description for candidate in candidates})}

    def previous_lifecycle():
        with TypeSafeClient(api_key="local-benchmark-only", base_url=base_url, timeout=15, retry=RetryPolicy(max_retries=0)) as client:
            response = client.system_one(state={"goal": "Inspect page", "observation": {"title": "Example"}, "history": []}, questions=questions, model="jev-latest")
        assert response.choices["aside_action"].choice == "inspect"

    def pooled_lifecycle():
        choice, _, _ = jev.choose_live(candidates, goal="Inspect page", observation={"title": "Example"}, api_key="local-benchmark-only")
        assert choice == "inspect"

    try:
        previous = measure(previous_lifecycle, samples, server)
        pooled = measure(pooled_lifecycle, samples, server)
        assert previous["http_requests"] == pooled["http_requests"] == samples
        assert previous["tcp_connections"] == samples
        assert pooled["tcp_connections"] == 1
        return {
            "scope": "Actual SDK against a temporary 127.0.0.1 keep-alive HTTP fixture; no artificial delay, no remote provider, no paid requests. Includes first connection in each group.",
            "per_request_client": previous,
            "shared_client": pooled,
            "p50_reduction_percent": round((1 - pooled["p50_ms"] / previous["p50_ms"]) * 100, 1),
            "caveat": "Local transport overhead only. This does not measure or predict live Jev inference latency.",
        }
    finally:
        jev.close_clients()
        if previous_base_url is None:
            os.environ.pop("TYPESAFE_BASE_URL", None)
        else:
            os.environ["TYPESAFE_BASE_URL"] = previous_base_url
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=30)
    arguments = parser.parse_args()
    if not 5 <= arguments.samples <= 1000:
        parser.error("--samples must be between 5 and 1000")
    print(json.dumps(benchmark(arguments.samples), indent=2))
