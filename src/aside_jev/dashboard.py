"""명시적으로 실행하는 localhost 전용 결정 작업 공간."""
from __future__ import annotations

import json
import os
import secrets
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from typing import Any

from . import __version__

MAX_BODY = 131_072
STATIC = {"/": ("index.html", "text/html"), "/app.css": ("app.css", "text/css"),
          "/app.js": ("app.js", "text/javascript"),
          "/i18n.mjs": ("i18n.mjs", "text/javascript"),
          "/demo.mjs": ("demo.mjs", "text/javascript")}


def runtime_status() -> dict[str, Any]:
    return {
        "version": __version__,
        "live_available": bool((os.environ.get("TYPESAFE_API_KEY") or os.environ.get("TYPESAFEAI_API_KEY", "")).strip()),
        "aside_available": bool(shutil.which("aside") or (
            os.path.isfile(os.environ.get("ASIDE_BIN", ""))
            and os.access(os.environ.get("ASIDE_BIN", ""), os.X_OK))),
        "model": "jev-latest",
        "timeout_s": 15,
        "execution": "decision_only",
    }


def decide_request(data: Any) -> dict[str, Any]:
    from .mcp_server import jev_step

    if not isinstance(data, dict):
        raise ValueError("요청은 JSON 객체여야 합니다.")
    allowed = {"goal", "observation", "candidates", "provider", "model", "min_confidence", "timeout_s"}
    if set(data) - allowed:
        raise ValueError("지원하지 않는 요청 항목이 있습니다.")
    goal = data.get("goal")
    if not isinstance(goal, str) or not goal.strip() or len(goal) > 4000:
        raise ValueError("목표를 1~4,000자로 입력해 주세요.")
    if data.get("provider") not in ("mock", "live"):
        raise ValueError("실행 모드는 mock 또는 live여야 합니다.")
    if not isinstance(data.get("observation"), (dict, str)):
        raise ValueError("관찰 정보는 JSON 객체 또는 문자열이어야 합니다.")
    if not isinstance(data.get("candidates"), list) or not data["candidates"]:
        raise ValueError("실행 후보를 한 개 이상 입력해 주세요.")
    model = data.get("model", "jev-latest")
    if not isinstance(model, str) or not model.strip() or len(model) > 100:
        raise ValueError("모델 이름을 1~100자로 입력해 주세요.")
    for name in ("min_confidence", "timeout_s"):
        if name in data and (isinstance(data[name], bool) or not isinstance(data[name], (int, float))):
            raise ValueError("신뢰도와 대기 한도는 숫자여야 합니다.")
    return jev_step(**{**data, "goal": goal.strip()})


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port: int = 8766):
        self.session_token = secrets.token_urlsafe(32)
        self.decisions = threading.BoundedSemaphore(4)
        super().__init__(("127.0.0.1", port), DashboardHandler)


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardServer

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format: str, *args: Any) -> None:
        # 입력·관찰·키가 액세스 로그에 기록되지 않도록 한다.
        pass

    def _send(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, status: int, data: dict[str, Any]) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False, allow_nan=False).encode())

    def _local_request(self) -> bool:
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host", "") not in hosts:
            self._json(403, {"error": "localhost에서만 사용할 수 있습니다.", "code": "origin"})
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{host}" for host in hosts}:
            self._json(403, {"error": "같은 작업 화면에서 요청해 주세요.", "code": "origin"})
            return False
        return True

    def do_GET(self) -> None:
        if not self._local_request():
            return
        if self.path == "/api/config":
            self._json(200, {**runtime_status(), "session_token": self.server.session_token})
        elif self.path in STATIC:
            filename, mime = STATIC[self.path]
            self._send(200, files("aside_jev").joinpath("static", filename).read_bytes(), mime)
        else:
            self._json(404, {"error": "페이지를 찾을 수 없습니다.", "code": "not_found"})

    def do_POST(self) -> None:
        if not self._local_request():
            return
        if self.path != "/api/decide":
            self._json(404, {"error": "지원하지 않는 요청입니다.", "code": "not_found"})
            return
        if not secrets.compare_digest(self.headers.get("X-Jev-Session", ""), self.server.session_token):
            self._json(403, {"error": "화면을 새로고침한 뒤 다시 시도해 주세요.", "code": "session"})
            return
        if self.headers.get_content_type() != "application/json":
            self._json(415, {"error": "JSON 형식으로 입력해 주세요.", "code": "input"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= MAX_BODY:
            self._json(413, {"error": "입력 크기는 128 KiB 이하여야 합니다.", "code": "input"})
            return
        if not self.server.decisions.acquire(blocking=False):
            self._json(429, {"error": "진행 중인 결정이 있습니다. 잠시 후 다시 시도해 주세요.", "code": "busy"})
            return
        try:
            data = json.loads(self.rfile.read(length))
            result = decide_request(data)
            self._json(200, result)
        except (ValueError, TypeError, KeyError):
            self._json(422, {"error": "입력을 확인해 주세요. 목표·후보 ID·관찰 정보와 설정 값이 올바른지 확인하세요.", "code": "input"})
        except Exception as exc:
            code = getattr(exc, "code", "unavailable")
            if type(exc).__name__ == "JevConfigurationError":
                code = "configuration"
            messages = {
                "configuration": "터미널에 TYPESAFE_API_KEY를 설정한 후 작업 공간을 다시 실행해 주세요.",
                "timeout": "응답 대기 한도를 초과했습니다. 설정에서 한도를 늘리거나 다시 시도해 주세요.",
                "authentication": "Jev 인증을 확인해 주세요. 터미널의 API 키를 갱신한 후 다시 실행하세요.",
                "rate_limit": "Jev 요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.",
                "busy": "다른 결정이 진행 중입니다. 잠시 후 다시 시도해 주세요.",
                "invalid_response": "Jev 응답을 검증하지 못했습니다. 후보를 확인한 후 다시 시도해 주세요.",
                "invalid_request": "Jev가 요청을 거부했습니다. 모델 이름과 입력 형식을 확인해 주세요.",
                "unavailable": "Jev에 연결하지 못했습니다. 연결 상태를 확인한 후 다시 시도해 주세요.",
            }
            code = code if code in messages else "unavailable"
            self._json(504 if code == "timeout" else 503, {"error": messages[code], "code": code})
        finally:
            self.server.decisions.release()


def serve_dashboard(port: int = 8766, *, open_browser: bool = False, locale: str = "en") -> None:
    from .jev import close_clients
    from .cli_i18n import text
    # 첫 클릭에서 MCP 모듈을 불러오느라 기다리지 않도록 시작 시 준비한다.
    from . import mcp_server  # noqa: F401

    with DashboardServer(port) as server:
        url = f"http://127.0.0.1:{server.server_port}"
        print(text("server_start", locale, url=url), flush=True)
        if open_browser:
            import webbrowser
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n" + text("server_stop", locale), flush=True)
        finally:
            close_clients()
