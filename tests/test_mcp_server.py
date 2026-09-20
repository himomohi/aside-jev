import asyncio
import threading

import pytest

from aside_jev import mcp_server
from aside_jev.core import Candidate

CANDIDATES = [{"id": "a", "description": "A", "tool": "click", "arguments": {"ref": "1"}}]


def test_sync_step_keeps_original_payload_and_adds_measured_timings():
    result = mcp_server.jev_step(goal="Goal", observation={}, candidates=CANDIDATES, provider="mock")
    assert result["execute"] == {"tool": "click", "arguments": {"ref": "1"}, "should_execute": True}
    assert set(result["timing_ms"]) == {"preparation", "decision", "total"}
    assert result["timing_ms"]["total"] >= result["timing_ms"]["decision"]
    assert result["request_policy"]["result_cache"] is False


def test_low_confidence_payload_is_abstain_and_preserves_telemetry(monkeypatch):
    monkeypatch.setattr(mcp_server, "decide", lambda *args, **kwargs: (Candidate("a", "A", tool="click"), 0.2, {"a": 0.2}))
    result = mcp_server.jev_step(goal="Goal", observation={}, candidates=CANDIDATES, provider="mock", min_confidence=0.8)
    assert result["choice_id"] == "abstain"
    assert result["suggested_choice_id"] == "a"
    assert result["execute"]["should_execute"] is False
    assert result["execute"]["tool"] is None
    assert result["timing_ms"]
    assert result["context"]


def test_invalid_provider_and_threshold_do_not_call_decide(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("must reject before deciding")
    monkeypatch.setattr(mcp_server, "decide", forbidden)
    for kwargs in ({"provider": "typo"}, {"min_confidence": float("nan")}):
        with pytest.raises(ValueError):
            mcp_server.jev_step(goal="Goal", observation={}, candidates=CANDIDATES, **kwargs)


def test_mcp_remains_responsive_during_slow_provider(monkeypatch):
    started, release = threading.Event(), threading.Event()
    def slow(*args, **kwargs):
        started.set()
        assert release.wait(3)
        return {"choice_id": "a"}
    monkeypatch.setattr(mcp_server, "jev_choose", slow)

    async def scenario():
        tool = mcp_server.mcp._tool_manager.get_tool("jev_choose")
        pending = asyncio.create_task(tool.run({"goal": "Goal", "observation": {}, "candidates": CANDIDATES}))
        try:
            assert await asyncio.to_thread(started.wait, 1)
            validation = await asyncio.wait_for(mcp_server.mcp._tool_manager.get_tool("jev_validate").run({"choice_id": "a", "candidates": CANDIDATES}), timeout=0.5)
            assert validation["ok"] is True
            assert not pending.done()
        finally:
            release.set()
        assert (await pending)["choice_id"] == "a"
    asyncio.run(scenario())


def test_mcp_tool_names_are_stable():
    names = {tool.name for tool in mcp_server.mcp._tool_manager.list_tools()}
    assert names == {"jev_system_one", "jev_choose", "jev_validate", "jev_step", "jev_extension_status", "jev_browser_run"}


def test_browser_connection_uses_total_deadline_and_releases_lock(monkeypatch):
    from contextlib import asynccontextmanager
    from aside_jev import browser_runtime
    @asynccontextmanager
    async def slow_connection():
        await asyncio.sleep(10)
        raise AssertionError("must time out before entering the browser loop")
        yield
    monkeypatch.setattr(browser_runtime, "connect_aside", slow_connection)
    result = asyncio.run(mcp_server._mcp_browser_run(goal="Read details", target_id="tab1",
        action_rules=[{"role":"link","name":"Continue","action":"click"}], completion_text="done", total_timeout_s=1))
    assert result["status"] == "time_budget"
    assert not mcp_server._browser_lock.locked()


def test_mcp_step_discards_decision_after_off(monkeypatch):
    monkeypatch.setattr(mcp_server, "decision_options", lambda **kw: {"provider":"live","model":"jev-latest","timeout_s":15,"min_confidence":.7})
    monkeypatch.setattr(mcp_server, "jev_step", lambda **kw: {"choice_id":"a"})
    def off():
        raise RuntimeError("OFF")
    monkeypatch.setattr(mcp_server, "active_policy", off)
    with pytest.raises(RuntimeError, match="OFF"):
        asyncio.run(mcp_server._mcp_step(goal="Goal", observation={}, candidates=CANDIDATES))


def test_mcp_step_discards_decision_after_threshold_increase(monkeypatch):
    monkeypatch.setattr(mcp_server, "decision_options", lambda **kw: {"provider":"live","model":"jev-latest","timeout_s":15,"min_confidence":.7})
    monkeypatch.setattr(mcp_server, "jev_step", lambda **kw: {"choice_id":"a","confidence":.8})
    monkeypatch.setattr(mcp_server, "active_policy", lambda: {"min_confidence":.99})
    with pytest.raises(RuntimeError, match="settings changed"):
        asyncio.run(mcp_server._mcp_step(goal="Goal", observation={}, candidates=CANDIDATES))
