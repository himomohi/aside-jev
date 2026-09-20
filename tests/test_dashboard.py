import json
import threading

import httpx
import pytest

from aside_jev.dashboard import DashboardServer


@pytest.fixture
def dashboard(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFEAI_API_KEY", raising=False)
    with DashboardServer(0) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False) as client:
                config = client.get("/api/config").json()
                client.headers["X-Jev-Session"] = config["session_token"]
                yield client, server
        finally:
            server.shutdown()
            thread.join(timeout=5)


def request_body():
    return {"goal": "다음 행동 선택", "observation": {"empty": True}, "provider": "mock",
            "candidates": [{"id": "fill", "description": "Fill field", "tool": "aside_type", "arguments": {"text": "example"}}],
            "min_confidence": 0.7, "timeout_s": 15}


def test_dashboard_assets_and_status(dashboard):
    client, server = dashboard
    assert server.server_address[0] == "127.0.0.1"
    for path in ("/", "/app.css", "/app.js", "/i18n.mjs", "/demo.mjs"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    page = client.get("/").text
    assert 'lang="en"' in page
    assert 'id="language-select"' in page
    assert 'type="module"' in page
    assert 'value="ko"' in page
    config = client.get("/api/config").json()
    assert not config["live_available"]
    assert config["execution"] == "decision_only"
    assert client.get("/../../pyproject.toml").status_code == 404


def test_mock_decision_has_timings_and_never_executes(dashboard, monkeypatch):
    from aside_jev import aside_bridge
    monkeypatch.setattr(aside_bridge, "aside_repl", lambda *a, **k: pytest.fail("화면은 브라우저 동작을 실행하면 안 됩니다"))
    client, _ = dashboard
    response = client.post("/api/decide", json=request_body())
    assert response.status_code == 200
    result = response.json()
    assert result["choice_id"] == "fill"
    assert result["provider"] == "mock"
    assert result["execute"]["tool"] == "aside_type"
    assert result["timing_ms"]["total"] >= result["timing_ms"]["decision"] >= 0
    assert "abstain" in result["probabilities"]


@pytest.mark.parametrize("bad", [
    {"provider": "liv"}, {"goal": " "}, {"candidates": []}, {"observation": []},
    {"timeout_s": 0}, {"timeout_s": True}, {"min_confidence": 2}, {"api_key": "sentinel"},
    {"candidates": [{"id": "a"}, {"id": "a"}]},
    {"candidates": [{"id": "abstain", "tool": "click"}]},
])
def test_invalid_input_rejected(dashboard, bad):
    client, _ = dashboard
    response = client.post("/api/decide", json={**request_body(), **bad})
    assert response.status_code == 422
    assert response.json()["code"] == "input"


def test_cross_origin_and_session_protection(dashboard):
    client, _ = dashboard
    assert client.get("/api/config", headers={"Host": "malicious.example"}).status_code == 403
    assert client.post("/api/decide", json=request_body(), headers={"Origin": "https://malicious.example"}).status_code == 403
    assert client.post("/api/decide", json=request_body(), headers={"X-Jev-Session": "wrong"}).status_code == 403
    assert client.options("/api/decide", headers={"Origin": "https://malicious.example"}).status_code != 200


def test_body_limits_and_json_errors(dashboard):
    client, _ = dashboard
    assert client.post("/api/decide", content="{}", headers={"Content-Type": "text/plain"}).status_code == 415
    assert client.post("/api/decide", content="not-json", headers={"Content-Type": "application/json"}).status_code == 422
    assert client.post("/api/decide", json={"padding": "a" * 131072}).status_code == 413


def test_live_without_key_is_actionable(dashboard):
    client, _ = dashboard
    response = client.post("/api/decide", json={**request_body(), "provider": "live"})
    assert response.status_code == 503
    assert response.json()["code"] == "configuration"
    assert "TYPESAFE_API_KEY" in response.json()["error"]


def test_upstream_failure_never_leaks_secrets(dashboard, monkeypatch):
    from aside_jev import mcp_server
    def fail(**kwargs):
        raise RuntimeError("private-provider-response sentinel-secret")
    monkeypatch.setattr(mcp_server, "jev_step", fail)
    client, _ = dashboard
    response = client.post("/api/decide", json=request_body())
    assert response.status_code == 503
    assert "sentinel" not in response.text
    assert "private-provider" not in response.text


def test_busy_server_rejects_new_work_and_health_remains_available(dashboard):
    client, server = dashboard
    for _ in range(4):
        server.decisions.acquire()
    try:
        assert client.post("/api/decide", json=request_body()).status_code == 429
        assert client.get("/api/config").status_code == 200
    finally:
        for _ in range(4):
            server.decisions.release()
