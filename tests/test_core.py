import pytest

from aside_jev.core import Candidate, build_abstain, classify, validate_choice
from aside_jev.jev import choose_mock
from aside_jev.loop import decide


def test_validate_rejects_unknown():
    cands = [Candidate("a", "A"), build_abstain()]
    with pytest.raises(ValueError):
        validate_choice("nope", cands)


def test_mock_prefers_non_abstain():
    cands = [
        Candidate("click-ok", "Click OK", tool="click", arguments={"ref": "1"}),
        build_abstain(),
    ]
    choice, conf, probs = choose_mock(cands)
    assert choice == "click-ok"
    assert conf == 1.0
    assert probs["click-ok"] == 1.0


def test_decide_mock_roundtrip():
    cands = [
        Candidate("type-email", "Type email", tool="type", arguments={"text": "a@b.c"}),
        build_abstain(),
    ]
    cand, conf, _ = decide(
        cands,
        goal="login",
        observation={"url": "https://x"},
        provider="mock",
    )
    assert cand.id == "type-email"
    assert cand.tool == "type"
    assert conf == 1.0


def test_classify():
    assert classify("tok", "tok", steps=1, max_steps=3) == "verified"
    assert classify("bad", "tok", steps=1, max_steps=3) == "refuted"
    assert classify(None, "tok", steps=3, max_steps=3) == "budget_exhausted"
    assert classify(None, "tok", steps=1, max_steps=3) == "unknown"
