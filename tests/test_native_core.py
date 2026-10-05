"""Rust/Python parity and real localhost transport, without paid Jev calls."""
import json
import random
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from aside_jev import jev
from aside_jev.browser_flow import _compact_lines_python
from aside_jev.native_core import native

pytestmark = pytest.mark.skipif(native is None, reason="Install the native extra to test Rust")


@pytest.mark.parametrize("tree", [
    "Ა Georgian\nᎠ Cherokee\nİ Turkish", "", "\n", "\r\n", "a\n\n", "a\rb\vc\fd\x1ce\x1df\x1eg\x85h\u2028i\u2029",
    '- link "Straße 완료" [ref=f2e3]\n' + '\n'.join(f'- text "noise {i}"' for i in range(6000)),
    ('x' * 801 + '\n') * 20 + ('완료 ' * 30 + '\n') * 200,
    '\n'.join(f'- text "{i}" [ref=e{i}]' for i in range(700)),
])
def test_compaction_and_references_match_python(tree):
    names, terms = {"strasse", "완료"}, {"link", "text", "noise"}
    assert native.compact_lines(tree, list(names), list(terms)) == _compact_lines_python(tree, names, terms)
    from aside_jev.browser_runtime import REF
    assert native.normalize_refs(tree) == REF.sub("[ref]", tree)


def test_budget_and_ranking_parity_with_random_unicode_pages():
    rng = random.Random(19)
    for _ in range(30):
        tree = '\n'.join(rng.choice(["Straße", "완료", "next", "text", "noise", "\\\""]) * rng.randrange(1, 250)
                         + f" [ref=e{i}]" for i in range(300))
        names, terms = {"strasse", "next"}, {"완료", "text"}
        assert native.compact_lines(tree, list(names), list(terms)) == _compact_lines_python(tree, names, terms)


def test_isolated_js_surrogate_preserves_local_processing(monkeypatch):
    import aside_jev.browser_flow as flow
    from aside_jev.browser_runtime import Observation
    tree = '- link "Continue" [ref=e1]\n- text "\ud800"'
    observation = Observation("https://example.test", tree)
    assert observation.identity == 'https://example.test\n- link "Continue" [ref]\n- text "\ud800"'
    kwargs = {"goal": "Continue", "rules": [flow.ActionRule("link", "Continue", "click")], "completion_text": "Finished"}
    rust_result = flow.compact_observation(observation, **kwargs)
    monkeypatch.setattr(flow, "native", None)
    assert rust_result == flow.compact_observation(observation, **kwargs)


@pytest.fixture
def provider(monkeypatch):
    class Server(ThreadingHTTPServer):
        daemon_threads = True
        requests = []
        connections = 0
        status = 200
        delay = 0
        body_delay = 0
        payload = None
        def get_request(self):
            connection, address = super().get_request()
            connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.connections += 1
            return connection, address

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.server.requests.append((self.path, self.headers.get("Authorization"), body))
            time.sleep(self.server.delay)
            answers = {}
            for name, q in body["questions"].items():
                if q["type"] == "choice":
                    choice = next(iter(q["criteria"]))
                    answers[name] = {"type": "choice", "choice": choice, "confidence": .9, "probabilities": {choice: .9}}
                elif q["type"] == "score":
                    answers[name] = {"type": "score", "score": 1.2, "confidence": .8,
                                     "probabilities": {"0": .2, "1": .4, "2": .4}, "legend": {"0": "low", "1": "mid", "2": "high"}}
                else:
                    answers[name] = {"type": "noul", "noul": .2}
            payload = json.dumps({"model": "local-only", "usage": {}, "answers": answers}).encode()
            if self.server.payload is not None:
                payload = self.server.payload
            self.send_response(self.server.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            if self.server.status == 307:
                self.send_header("Location", "/redirected")
            self.end_headers()
            time.sleep(self.server.body_delay)
            try:
                self.wfile.write(payload)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
        def log_message(self, *_):
            pass

    server = Server(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    jev.close_clients()
    monkeypatch.setenv("TYPESAFE_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("TYPESAFE_API_KEY", "local-test-only")
    yield server
    jev.close_clients()
    server.shutdown()
    server.server_close()
    thread.join(3)


def call(**kwargs):
    return jev.system_one({"token": "hidden", "text": "hello"}, {
        "next": {"type": "choice", "criteria": {"inspect": "Inspect", "abstain": "Stop"}},
        "risk": {"type": "score", "criteria": ["low", "mid", "high"]},
        "done": {"type": "noul", "instructions": "Completed?"},
    }, **kwargs)


def test_real_rust_transport_reuses_connection_and_preserves_sdk_wire(provider):
    for _ in range(5):
        response = call()
        assert response["answers"]["next"]["choice"] == "inspect"
        assert response["answers"]["risk"]["score"] == 1.2
        assert response["answers"]["done"]["noul"] == .2
    assert len(provider.requests) == 5
    assert provider.connections == 1
    path, auth, body = provider.requests[0]
    assert path == "/v1/systemone"
    assert auth == "Bearer local-test-only"
    assert "hidden" not in json.dumps(body)


def test_rust_concurrent_requests_release_gil(provider):
    provider.delay = .05
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: call(), range(4)))
    assert len(responses) == len(provider.requests) == 4


@pytest.mark.parametrize("status,code", [(401, "authentication"), (429, "rate_limit"), (503, "unavailable"), (307, "unavailable")])
def test_rust_errors_and_redirects_never_retry(provider, status, code):
    provider.status = status
    with pytest.raises(jev.JevProviderError) as error:
        call()
    assert error.value.code == code
    assert "local-test-only" not in str(error.value)
    assert len(provider.requests) == 1


def test_rust_timeout_is_bounded_and_never_retried(provider):
    provider.delay = 1.2
    with pytest.raises(jev.JevProviderError) as error:
        call(timeout_s=1)
    assert error.value.code == "timeout"
    assert len(provider.requests) == 1


def test_rust_deadline_includes_response_body(provider):
    provider.body_delay = 1.2
    with pytest.raises(jev.JevProviderError) as error:
        call(timeout_s=1)
    assert error.value.code == "timeout"
    assert len(provider.requests) == 1


@pytest.mark.parametrize("payload,code", [
    (b'{"model":"local","usage":{},"answers":{}}', "invalid_response"),
    (b"x" * 2_000_001, "unavailable"),
])
def test_rust_invalid_or_oversized_response_never_returns_answer(provider, payload, code):
    provider.payload = payload
    with pytest.raises(jev.JevProviderError) as error:
        call()
    assert error.value.code == code
    assert len(provider.requests) == 1
