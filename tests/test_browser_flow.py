import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from aside_jev.browser_flow import ActionRule, action_table, compact_observation, run_browser_flow
from aside_jev.browser_runtime import AsideRuntime, BrowserRuntimeError, Observation
from aside_jev.jev import JevProviderError

RULES = [{"role": "link", "name": "Continue", "action": "click"}]


def page(number=0, ref="e1", text=""):
    return Observation(f"https://example.test/{number}", f'- title: "Step {number}"\n- link "Continue" [ref={ref}]\n{text}')


class Runtime:
    def __init__(self, pages):
        self.pages = list(pages)
        self.current = self.pages.pop(0)
        self.actions = []

    async def attach(self, target_id):
        return self.current

    async def execute(self, action, expected, *, timeout_ms):
        assert expected == self.current
        self.actions.append(action)
        self.current = self.pages.pop(0)
        return self.current


def pick(**kwargs):
    ids = [row.id for row in kwargs["candidates"]]
    return ("finish" if "finish" in ids else ids[0], .95, {})


def run(runtime, **kwargs):
    return asyncio.run(run_browser_flow(runtime, goal="Continue until Journey complete", target_id="tab1", action_rules=RULES,
                                       completion_text="Journey complete", decision=pick, **kwargs))


def test_six_page_transitions_rebuild_refs_and_verify():
    runtime = Runtime([page(n, ref=f"e{n+1}", text="Journey complete" if n == 6 else "") for n in range(7)])
    result = run(runtime)
    assert result["status"] == "verified"
    assert len(runtime.actions) == 6
    assert len(result["steps"]) == 7
    assert result["automatic_fallback"] is False
    assert result["provider"] == "live"


def test_repeated_page_action_stops_navigation_cycle():
    runtime = Runtime([page(0), page(1), page(0, ref="e8"), page(1)])
    result = run(runtime)
    assert result["status"] == "loop_detected"
    assert len(runtime.actions) == 2


def test_ref_changes_alone_are_not_progress():
    runtime = Runtime([page(), page(ref="e25")])
    assert run(runtime)["status"] == "no_progress"
    assert len(runtime.actions) == 1


def test_stale_state_never_executes():
    runtime = Runtime([page(), None])
    result = run(runtime)
    assert result["status"] == "stale_observation"
    assert result["steps"][0]["executed"] is False


def test_step_budget_does_not_claim_success():
    runtime = Runtime([page(0), page(1)])
    result = run(runtime, max_steps=1)
    assert result["status"] == "step_budget"
    assert result["verified"] is False


def test_completion_requires_exact_url_and_visible_text():
    runtime = Runtime([page(0, text="Journey complete")])
    result = run(runtime, completion_url="https://example.test/0")
    assert result["verified"]
    assert runtime.actions == []
    runtime = Runtime([page(0, text="Journey complete"), page(1)])
    assert run(runtime, completion_url="https://example.test/wrong", max_steps=1)["status"] == "step_budget"


def test_completion_changed_during_decision_is_not_verified():
    class Changed(Runtime):
        count = 0
        async def attach(self, target_id):
            self.count += 1
            return self.current if self.count == 1 else page(8)
    assert run(Changed([page(text="Journey complete")]))["status"] == "stale_observation"


@pytest.mark.parametrize("choice,confidence,expected", [("made-up", .99, "invalid_choice"), ("action-0", .2, "abstained"), ("abstain", .99, "abstained")])
def test_bad_choice_or_low_confidence_never_executes(choice, confidence, expected):
    runtime = Runtime([page()])
    result = asyncio.run(run_browser_flow(runtime, goal="Read details", target_id="tab1", action_rules=RULES,
        completion_text="Journey complete", decision=lambda **_: (choice, confidence, {})))
    assert result["status"] == expected
    assert runtime.actions == []


def test_toggle_off_during_decision_discards_result():
    runtime = Runtime([page()])
    enabled = True
    def policy():
        if not enabled:
            raise RuntimeError("OFF")
    def turn_off(**kwargs):
        nonlocal enabled
        enabled = False
        return pick(**kwargs)
    result = asyncio.run(run_browser_flow(runtime, goal="Read details", target_id="tab1", action_rules=RULES,
        completion_text="Journey complete", policy_check=policy, decision=turn_off))
    assert result["status"] == "stopped"
    assert runtime.actions == []


def test_provider_error_stops_without_fallback():
    def failure(**_):
        raise JevProviderError("fake", code="timeout")
    runtime = Runtime([page()])
    result = asyncio.run(run_browser_flow(runtime, goal="Read details", target_id="tab1", action_rules=RULES,
        completion_text="Journey complete", decision=failure))
    assert result["status"] == "provider_error"
    assert result["error"] == "timeout"
    assert runtime.actions == []


def test_total_deadline_prevents_late_execution():
    def slow(**kwargs):
        time.sleep(1.05)
        return pick(**kwargs)
    runtime = Runtime([page()])
    result = asyncio.run(run_browser_flow(runtime, goal="Read details", target_id="tab1", action_rules=RULES,
        completion_text="Journey complete", total_timeout_s=1, decision=slow))
    assert result["status"] == "time_budget"
    assert runtime.actions == []


def test_no_matching_or_duplicate_elements_need_input():
    for tree in ['- button "Unauthorized" [ref=e1]', '- link "Continue" [ref=e1]\n- link "Continue" [ref=e2]']:
        runtime = Runtime([Observation("https://example.test", tree)])
        assert run(runtime)["status"] == "needs_input"
        assert runtime.actions == []


def test_large_page_keeps_relevant_tail_and_reports_omission():
    observation = page(text="\n".join(f'- text: "Unrelated {n}"' for n in range(5000)) + '\n- heading "Journey complete"')
    state = compact_observation(observation, goal="Journey complete", rules=[ActionRule.parse(RULES[0])], completion_text="Journey complete")
    assert "Journey complete" in json.dumps(state)
    assert "Continue" in json.dumps(state)
    assert state["omitted_lines"] > 4900
    assert len(json.dumps(state, ensure_ascii=False)) < 6500


def test_fill_value_is_supplied_and_never_invented():
    obs = Observation("https://example.test", '- textbox "Query" [ref=f1e2]')
    rule = ActionRule.parse({"role": "textbox", "name": "Query", "action": "fill", "value": "A \"quoted\" value"})
    assert action_table(obs, [rule])[0]["arguments"]["value"] == rule.value
    with pytest.raises(ValueError):
        ActionRule.parse({"role": "textbox", "name": "Query", "action": "fill"})


def test_distinct_fill_values_are_distinguishable_to_jev():
    from aside_jev.core import criteria_map, parse_candidates
    rules = [ActionRule.parse({"role": "textbox", "name": "Query", "action": "fill", "value": value}) for value in ("cats", "dogs")]
    criteria = criteria_map(parse_candidates(action_table(Observation("https://example.test", '- textbox "Query" [ref=e1]'), rules)))
    assert "cats" in criteria["action-0"]
    assert "dogs" in criteria["action-1"]


@pytest.mark.parametrize("name,values", [("Search", ["token=aaa", "token=bbb"]), ("N"*300, ['"'*998+'a', '"'*998+'b'])])
def test_colliding_sanitized_fill_candidates_stop_before_jev(name, values):
    runtime = Runtime([Observation("https://example.test", f'- textbox "{name}" [ref=e1]')])
    def forbidden(**_):
        raise AssertionError("Ambiguous candidates must not reach Jev")
    result = asyncio.run(run_browser_flow(runtime, goal="Search", target_id="tab1", completion_text="Finished",
        action_rules=[{"role":"textbox","name":name,"action":"fill","value":value} for value in values], decision=forbidden))
    assert result["status"] == "needs_input"
    assert runtime.actions == []


def test_long_url_cannot_remove_context_accounting():
    observation = Observation("https://example.test/" + "x" * 1970, '\n'.join('- text: "' + str(i) + 'x'*790+'"' for i in range(10)))
    state = compact_observation(observation, goal="x", rules=[ActionRule.parse(RULES[0])], completion_text="done")
    assert state["total_lines"] == 10
    assert state["omitted_lines"] == 10 - len(state["page_lines"])
    assert len(json.dumps(state, ensure_ascii=False)) < 6500


def test_threshold_increase_during_decision_blocks_action():
    runtime = Runtime([page()])
    threshold = .7
    def raise_threshold(**kwargs):
        nonlocal threshold
        threshold = .99
        return "action-0", .8, {}
    result = asyncio.run(run_browser_flow(runtime, goal="Read details", target_id="tab1", action_rules=RULES,
        completion_text="Journey complete", policy_check=lambda: {"min_confidence": threshold}, decision=raise_threshold))
    assert result["status"] == "abstained"
    assert runtime.actions == []


def test_runtime_parses_aside_preamble_and_rejects_unstructured_errors():
    class Session:
        async def call_tool(self, name, args):
            return SimpleNamespace(isError=False, content=[SimpleNamespace(type="text", text='Attached tab\n'+json.dumps({"marker":"aside-jev-runtime-v1","url":"https://example.test","tree":"snapshot"}))])
    assert asyncio.run(AsideRuntime(Session()).attach("tab1")).tree == "snapshot"
