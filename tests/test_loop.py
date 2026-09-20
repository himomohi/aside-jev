import pytest

from aside_jev import loop
from aside_jev.core import Candidate


def test_low_confidence_without_abstain_never_executes(monkeypatch):
    candidate = Candidate("pay", "Pay", tool="click", arguments={"ref": "pay"})
    monkeypatch.setattr(loop, "choose_live", lambda *args, **kwargs: ("pay", 0.3, {"pay": 0.3}))
    executed = []
    steps = loop.run_bounded_loop(
        config=loop.LoopConfig(goal="Pay", provider="live", min_confidence=0.8),
        observe=lambda: {}, propose=lambda _: [candidate], execute=executed.append,
        verify=lambda: "unknown",
    )
    assert not executed
    assert len(steps) == 1
    assert steps[0].choice_id == "abstain"
    assert steps[0].executed is False
    assert steps[0].outcome == "abstained"


def test_loop_bounds_history_and_reports_budget():
    history = [{"step": i} for i in range(50)]
    config = loop.LoopConfig(goal="Inspect", max_steps=2, history=history)
    candidate = Candidate("inspect", "Inspect", tool="snapshot")
    steps = loop.run_bounded_loop(
        config=config, observe=lambda: {}, propose=lambda _: [candidate],
        execute=lambda _: "ok", verify=lambda: "unknown",
    )
    assert steps[-1].outcome == "budget_exhausted"
    assert len(config.history) == 12
    assert all(step.timing_ms["total"] >= step.timing_ms["decision"] for step in steps)


@pytest.mark.parametrize("threshold", [-1, 1.1, float("nan"), float("inf"), True])
def test_invalid_confidence_threshold_stops_before_observation(threshold):
    def forbidden():
        raise AssertionError("must validate first")
    with pytest.raises(ValueError, match="min_confidence"):
        loop.run_bounded_loop(
            config=loop.LoopConfig(goal="Goal", min_confidence=threshold),
            observe=forbidden, propose=lambda _: [], execute=lambda _: None, verify=lambda: "unknown",
        )


def test_invalid_provider_never_falls_back_to_live(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("live provider must not be called")
    monkeypatch.setattr(loop, "choose_live", forbidden)
    with pytest.raises(ValueError, match="provider"):
        loop.decide([Candidate("a", "A")], goal="Goal", observation={}, provider="typo")
