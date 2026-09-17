from __future__ import annotations

import os
from typing import Any

from .core import Candidate, criteria_map, validate_choice


def choose_mock(candidates: list[Candidate], *, prefer: str | None = None) -> tuple[str, float, dict[str, float]]:
    """Deterministic chooser for credential-free CI and demos."""
    ids = [c.id for c in candidates]
    if not ids:
        raise ValueError("candidates must not be empty")
    if prefer and prefer in ids:
        selected = prefer
    else:
        selected = next((i for i in ids if i != "abstain"), ids[0])
    probs = {i: (1.0 if i == selected else 0.0) for i in ids}
    return selected, float(probs.get(selected, 0.0)), probs


def choose_live(
    candidates: list[Candidate],
    *,
    goal: str,
    observation: dict[str, Any] | str,
    history: list[dict[str, Any]] | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> tuple[str, float, dict[str, float]]:
    """Ask TypeSafe Jev to pick exactly one candidate id."""
    from typesafe_sdk import Choice, TypeSafeClient

    if not candidates:
        raise ValueError("candidates must not be empty")

    key = (
        api_key
        or os.environ.get("TYPESAFE_API_KEY")
        or os.environ.get("TYPESAFEAI_API_KEY")
    )
    if not key:
        raise RuntimeError(
            "TYPESAFE_API_KEY is required for live Jev. "
            "Export it, or use provider=mock for the offline path."
        )

    state: dict[str, Any] = {
        "goal": goal,
        "observation": observation,
        "history": history or [],
        "rule": "Return only one of the supplied candidate IDs. Never invent tools, refs, or arguments.",
    }
    questions = {
        "aside_action": Choice(
            instructions=(
                "Which complete executable action should the Aside agent run next? "
                "Pick exactly one candidate id from the criteria."
            ),
            criteria=criteria_map(candidates),
        )
    }

    with TypeSafeClient(api_key=key) as client:
        response = client.system_one(state=state, questions=questions, model=model)

    answer = response.answers["aside_action"]
    choice = str(answer.choice)
    validate_choice(choice, candidates)
    confidence = float(answer.confidence or 0.0)
    probs = {str(k): float(v) for k, v in dict(answer.probabilities or {}).items()}
    for c in candidates:
        probs.setdefault(c.id, 0.0)
    return choice, confidence, probs
