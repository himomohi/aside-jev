"""Side-effect-free boundary tests for explicitly authorized browser tasks."""
import pytest

from aside_jev.browser_policy import ActionRule, validate_completion


@pytest.mark.parametrize("text", ["", "   ", "\t\n ", "\u3000" * 3, "ab", " a ", "x" * 301, None, 123])
def test_invalid_completion_signal_is_rejected(text):
    with pytest.raises(ValueError, match="completion_text"):
        validate_completion(text, None)


@pytest.mark.parametrize("url", [
    "https://", "https:///done", "https://?done", "https://#done", "/done",
    "file:///done", "javascript:done", "https://example.test:bad/done",
    "https://example.test:65536/done", "https://example.test:0/done",
    "https://[::1/done", "https://exa mple.test/done", "https://example.test/\ndone",
    " https://example.test/done", "https://example.test/\x00done", 123,
])
def test_malformed_completion_url_is_rejected(url):
    with pytest.raises(ValueError, match="completion_url"):
        validate_completion("Journey complete", url)


@pytest.mark.parametrize("url", [
    None, "https://example.test/done?result=ok#summary",
    "http://127.0.0.1:8766/done", "http://[::1]:8766/done",
    "https://example.test/%20done", "https://example.test/완료",
])
def test_valid_completion_signals_are_accepted(url):
    validate_completion("Journey complete", url)
    validate_completion("  작업 완료  ", url)


@pytest.mark.parametrize("name", ["", "   ", "\t\n", "\u3000"])
def test_blank_accessible_names_are_rejected(name):
    with pytest.raises(ValueError, match="accessible name"):
        ActionRule.parse({"role": "button", "name": name, "action": "click"})


def test_action_names_and_fill_values_are_not_normalized():
    rule = ActionRule.parse({"role": "textbox", "name": "  Query  ", "action": "fill", "value": "  cats  "})
    assert rule.name == "  Query  "
    assert rule.value == "  cats  "
    cleared = ActionRule.parse({"role": "textbox", "name": "Query", "action": "fill", "value": ""})
    assert cleared.value == ""


@pytest.mark.parametrize("data", [
    {"role": "button", "name": "Submit", "action": "fill", "value": "x"},
    {"role": "textbox", "name": "Query", "action": "fill"},
    {"role": "button", "name": "Submit", "action": "click", "value": "x"},
    {"role": "button", "name": "Submit", "action": "evaluate"},
    {"role": "button", "name": "Submit", "action": "click", "selector": "#other"},
])
def test_rule_extraction_preserves_existing_restrictions(data):
    with pytest.raises(ValueError):
        ActionRule.parse(data)
