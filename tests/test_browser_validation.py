"""Invalid task inputs must stop before observation or model selection."""
import asyncio

import pytest

from aside_jev.browser_flow import ActionRule as FlowActionRule, run_browser_flow
from aside_jev.browser_policy import ActionRule


class UntouchedRuntime:
    async def attach(self, target_id):
        raise AssertionError("Invalid input must not reach browser observation")

    async def execute(self, *args, **kwargs):
        raise AssertionError("Invalid input must not execute a browser action")


def forbidden_decision(**kwargs):
    raise AssertionError("Invalid input must not reach Jev")


@pytest.mark.parametrize("overrides", [
    {"completion_text": "   "},
    {"completion_text": "\t\n "},
    {"completion_text": " a "},
    {"completion_url": "https://"},
    {"completion_url": "https://example.test:99999/done"},
    {"completion_url": "https://example.test/\ndone"},
    {"action_rules": [{"role": "button", "name": "   ", "action": "click"}]},
])
def test_invalid_task_never_reaches_browser_or_jev(overrides):
    options = {
        "goal": "Continue to the completion page",
        "target_id": "tab1",
        "action_rules": [{"role": "link", "name": "Continue", "action": "click"}],
        "completion_text": "Journey complete",
        "decision": forbidden_decision,
    }
    options.update(overrides)
    with pytest.raises(ValueError):
        asyncio.run(run_browser_flow(UntouchedRuntime(), **options))


def test_action_rule_import_remains_backwards_compatible():
    assert FlowActionRule is ActionRule
