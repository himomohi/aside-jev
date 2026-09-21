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

@pytest.mark.parametrize('case,expected', [('success','verified'),('provider','assessment_failed'),('observation_error','assessment_failed'),('low','assessment_uncertain'),('risk_low','assessment_uncertain'),('risk_high','assessment_uncertain'),('stale','stale_observation'),('timeout','time_budget')])
def test_browser_completion_requires_assessment_and_preserves_actions(monkeypatch, case, expected):
    from contextlib import asynccontextmanager
    from aside_jev import browser_runtime, browser_flow
    from aside_jev.browser_runtime import Observation
    class Runtime:
        reads = 0
        async def attach(self, target):
            self.reads += 1
            if case == 'observation_error':
                raise RuntimeError('private upstream error must not leak')
            if case == 'timeout':
                await asyncio.sleep(2)
            return Observation('https://fixture.test/', 'done' if case != 'stale' or self.reads == 1 else 'changed')
    @asynccontextmanager
    async def connection():
        yield Runtime()
    async def flow(*args, **kwargs):
        return {'verified':True,'status':'verified','steps':[{'executed':True,'choice_id':'action-0','execution_state':'confirmed','page_changed':True}], 'elapsed_ms':1, 'provider':'live'}
    def assessment(**kwargs):
        assert kwargs['state']['executed_action_trace'][0]['action']['name'] == 'go'
        assert kwargs['questions']['risk']['criteria'][0] == 'No sensitive action'
        assert set(kwargs['questions']['completed']['criteria']) == {'true','false'}
        if case == 'provider':
            raise RuntimeError('private upstream error must not leak')
        return {'answers':{'completed':{'noul':.2 if case == 'low' else .99},'risk':{'score':2 if case == 'risk_high' else 0,'confidence':.2 if case == 'risk_low' else .99}}}
    monkeypatch.setattr(browser_runtime,'connect_aside',connection)
    monkeypatch.setattr(browser_flow,'run_browser_flow',flow)
    monkeypatch.setattr(mcp_server,'jev_system_one',assessment)
    monkeypatch.setattr(mcp_server,'active_policy',lambda:None)
    output=asyncio.run(mcp_server._mcp_browser_run(goal='done',target_id='test',action_rules=[{'role':'button','name':'go','action':'click'}],completion_text='done',total_timeout_s=1))
    assert output['status']==expected
    assert output['verified'] is (case == 'success')
    assert output['browser_verified'] is True
    assert output['steps'][0]['executed'] is True
    assert 'private upstream' not in str(output)
    assert not mcp_server._browser_lock.locked()
