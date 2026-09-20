import json

import pytest

from aside_jev.aside_bridge import sanitize_context, summarize_history, summarize_observation


def test_nested_secrets_and_url_credentials_are_redacted_without_mutation():
    payload = {
        "page": {"api_key": "do-not-send", "items": [{"Authorization": "Bearer hidden"}]},
        "text": "password=hidden-secret https://user:pass@example.test/?access_token=hidden-token&view=main",
        "safe": "Submit order",
    }
    safe = summarize_observation(payload)
    encoded = json.dumps(safe)
    assert "do-not-send" not in encoded
    assert "hidden" not in encoded
    assert "user:pass" not in encoded
    assert safe["safe"] == "Submit order"
    assert payload["page"]["api_key"] == "do-not-send"


def test_context_is_bounded_for_escaped_strings_and_deep_objects():
    payload = {str(i): {"nodes": [{"text": '\\"\n' * 10000} for _ in range(60)]} for i in range(80)}
    bounded = summarize_observation(payload)
    assert len(json.dumps(bounded, ensure_ascii=False, separators=(",", ":"))) <= 12000
    assert len(json.dumps(summarize_observation('\n' * 50000))) <= 12000
    recursive = {}
    recursive["self"] = recursive
    assert "TRUNCATED" in json.dumps(summarize_observation(recursive))


def test_history_keeps_recent_entries_and_bounds_the_prompt():
    history = [{"step": i, "token": "hidden"} for i in range(30)]
    safe = summarize_history(history)
    assert [item["step"] for item in safe] == list(range(18, 30))
    assert "hidden" not in json.dumps(safe)
    heavy = [{"step": i, "result": "x" * 2000} for i in range(30)]
    safe = summarize_history(heavy)
    assert safe[-1]["step"] == 29
    assert len(json.dumps(safe, separators=(",", ":"))) <= 8000
    assert len(history) == 30


@pytest.mark.parametrize("payload", [{"x": float("nan")}, {"x": object()}, {1: "value"}])
def test_invalid_context_fails_before_provider(payload):
    with pytest.raises(ValueError):
        sanitize_context(payload)
