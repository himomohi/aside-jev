"""Early HTTP rejection must preserve the response without unbounded draining."""
from contextlib import contextmanager
from http.client import HTTPResponse
import io
import socket
import threading
from types import SimpleNamespace

import httpx
import pytest

from aside_jev.dashboard import DashboardHandler, DashboardServer, MAX_BODY, MAX_DISCARD


@contextmanager
def server():
    with DashboardServer(0) as instance:
        thread = threading.Thread(target=instance.serve_forever, daemon=True)
        thread.start()
        try:
            yield instance
        finally:
            instance.shutdown()
            thread.join(timeout=3)


@pytest.mark.parametrize("content_type,status", [("application/json", 413), ("text/plain", 415)])
def test_oversized_body_returns_error_without_connection_reset(content_type, status):
    with server() as instance, httpx.Client(trust_env=False, timeout=3) as client:
        response = client.post(f"http://127.0.0.1:{instance.server_port}/api/decide",
            content=b"a" * (MAX_BODY + 16), headers={"Content-Type": content_type,
            "X-Jev-Session": instance.session_token})
        assert response.status_code == status
        assert response.json()["code"] == "input"
        assert response.headers["Connection"] == "close"


def test_oversized_headers_receive_error_before_body_is_sent():
    with server() as instance, socket.create_connection(("127.0.0.1", instance.server_port), timeout=3) as client:
        client.sendall((f"POST /api/decide HTTP/1.1\r\nHost: 127.0.0.1:{instance.server_port}\r\n"
                        f"X-Jev-Session: {instance.session_token}\r\nContent-Type: application/json\r\n"
                        "Content-Length: 1000000000\r\n\r\n").encode())
        response = HTTPResponse(client)
        response.begin()
        assert response.status == 413
        assert response.read()


def test_rejected_body_discard_has_a_fixed_byte_limit():
    stream = io.BufferedReader(io.BytesIO(b"x" * (MAX_DISCARD + 1)))
    calls = []
    connection = SimpleNamespace(shutdown=lambda how: calls.append(how), settimeout=lambda _: None)
    handler = object.__new__(DashboardHandler)
    handler.connection, handler.rfile = connection, stream
    handler._discard_rejected_body()
    assert calls == [socket.SHUT_WR]
    assert stream.read() == b"x"
