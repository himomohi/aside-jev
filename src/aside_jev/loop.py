from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable, Literal

from .aside_bridge import summarize_history
from .core import Candidate, Outcome, build_abstain, validate_candidates, validate_choice, validate_confidence
from .jev import choose_live, choose_mock, prepare_decision_context, resolve_timeout

Provider = Literal["mock", "live"]


@dataclass
class StepResult:
    choice_id: str
    confidence: float
    probabilities: dict[str, float]
    candidate: Candidate
    executed: bool
    tool_result: Any = None
    outcome: Outcome | None = None
    timing_ms: dict[str, float] = field(default_factory=dict)


@dataclass
class LoopConfig:
    goal: str
    provider: Provider = "mock"
    max_steps: int = 8
    min_confidence: float = 0.0
    model: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    timeout_s: float | None = None


def decide(
    candidates: list[Candidate],
    *,
    goal: str,
    observation: dict[str, Any] | str,
    provider: Provider = "mock",
    history: list[dict[str, Any]] | None = None,
    model: str | None = None,
    prefer: str | None = None,
    timeout_s: float | None = None,
) -> tuple[Candidate, float, dict[str, float]]:
    if provider not in ("mock", "live"):
        raise ValueError("provider must be mock or live")
    validate_candidates(candidates)
    resolve_timeout(timeout_s)
    if provider == "mock":
        prepare_decision_context(goal, observation, history)
        choice, confidence, probs = choose_mock(candidates, prefer=prefer)
    else:
        choice, confidence, probs = choose_live(
            candidates,
            goal=goal,
            observation=observation,
            history=history,
            model=model,
            timeout_s=timeout_s,
        )
    candidate = validate_choice(choice, candidates)
    return candidate, validate_confidence(confidence), probs


def run_bounded_loop(
    *,
    config: LoopConfig,
    observe: Callable[[], dict[str, Any] | str],
    propose: Callable[[dict[str, Any] | str], list[Candidate]],
    execute: Callable[[Candidate], Any],
    verify: Callable[[], Outcome],
) -> list[StepResult]:
    """Observe → propose app-owned candidates → Jev picks id → execute → verify."""
    validate_confidence(config.min_confidence, name="min_confidence")
    if isinstance(config.max_steps, bool) or not isinstance(config.max_steps, int) or not 1 <= config.max_steps <= 1000:
        raise ValueError("max_steps must be an integer between 1 and 1000")
    if config.provider not in ("mock", "live"):
        raise ValueError("provider must be mock or live")
    resolve_timeout(config.timeout_s)
    config.history[:] = summarize_history(config.history)
    steps: list[StepResult] = []
    for i in range(config.max_steps):
        started = perf_counter()
        observation = observe()
        candidates = propose(observation)
        if not candidates:
            raise RuntimeError("propose() returned no candidates")
        decision_started = perf_counter()
        candidate, confidence, probs = decide(
            candidates,
            goal=config.goal,
            observation=observation,
            provider=config.provider,
            history=config.history,
            model=config.model,
            timeout_s=config.timeout_s,
        )
        decision_finished = perf_counter()
        if confidence < config.min_confidence and candidate.id != "abstain":
            candidate = validate_choice("abstain", candidates) if any(
                c.id == "abstain" for c in candidates
            ) else build_abstain("Confidence is below the required threshold.")

        executed = False
        tool_result = None
        if candidate.tool:
            tool_result = execute(candidate)
            executed = True
            config.history.append(
                {
                    "step": i + 1,
                    "choice": candidate.id,
                    "tool": candidate.tool,
                    "confidence": confidence,
                }
            )
            config.history[:] = summarize_history(config.history)

        outcome = verify()
        if candidate.id == "abstain" and outcome == "unknown":
            outcome = "abstained"
        elif i + 1 == config.max_steps and outcome == "unknown":
            outcome = "budget_exhausted"
        steps.append(
            StepResult(
                choice_id=candidate.id,
                confidence=confidence,
                probabilities=probs,
                candidate=candidate,
                executed=executed,
                tool_result=tool_result,
                outcome=outcome,
                timing_ms={
                    "preparation": round((decision_started - started) * 1000, 3),
                    "decision": round((decision_finished - decision_started) * 1000, 3),
                    "total": round((perf_counter() - started) * 1000, 3),
                },
            )
        )
        if outcome == "verified" or candidate.id == "abstain":
            break
        if outcome == "refuted":
            break
    return steps
