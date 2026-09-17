from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from .core import Candidate, Outcome, validate_choice
from .jev import choose_live, choose_mock

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


@dataclass
class LoopConfig:
    goal: str
    provider: Provider = "mock"
    max_steps: int = 8
    min_confidence: float = 0.0
    model: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)


def decide(
    candidates: list[Candidate],
    *,
    goal: str,
    observation: dict[str, Any] | str,
    provider: Provider = "mock",
    history: list[dict[str, Any]] | None = None,
    model: str | None = None,
    prefer: str | None = None,
) -> tuple[Candidate, float, dict[str, float]]:
    if provider == "mock":
        choice, confidence, probs = choose_mock(candidates, prefer=prefer)
    else:
        choice, confidence, probs = choose_live(
            candidates,
            goal=goal,
            observation=observation,
            history=history,
            model=model,
        )
    candidate = validate_choice(choice, candidates)
    return candidate, confidence, probs


def run_bounded_loop(
    *,
    config: LoopConfig,
    observe: Callable[[], dict[str, Any] | str],
    propose: Callable[[dict[str, Any] | str], list[Candidate]],
    execute: Callable[[Candidate], Any],
    verify: Callable[[], Outcome],
) -> list[StepResult]:
    """Observe → propose app-owned candidates → Jev picks id → execute → verify."""
    steps: list[StepResult] = []
    for i in range(config.max_steps):
        observation = observe()
        candidates = propose(observation)
        if not candidates:
            raise RuntimeError("propose() returned no candidates")
        candidate, confidence, probs = decide(
            candidates,
            goal=config.goal,
            observation=observation,
            provider=config.provider,
            history=config.history,
            model=config.model,
        )
        if confidence < config.min_confidence and candidate.id != "abstain":
            candidate = validate_choice("abstain", candidates) if any(
                c.id == "abstain" for c in candidates
            ) else candidate

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

        outcome = verify()
        steps.append(
            StepResult(
                choice_id=candidate.id,
                confidence=confidence,
                probabilities=probs,
                candidate=candidate,
                executed=executed,
                tool_result=tool_result,
                outcome=outcome,
            )
        )
        if outcome == "verified" or candidate.id == "abstain":
            break
        if outcome == "refuted":
            break
    return steps
