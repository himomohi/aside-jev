from __future__ import annotations

import os
from typing import Any

from .core import Candidate, criteria_map, validate_choice

DEFAULT_MODEL = "jev-latest"


def _resolve_api_key(api_key: str | None = None) -> str:
    key = (
        api_key
        or os.environ.get("TYPESAFE_API_KEY")
        or os.environ.get("TYPESAFEAI_API_KEY")
    )
    if not key:
        raise RuntimeError(
            "TYPESAFE_API_KEY is required for live Jev "
            "(https://docs.typesafe.ai). Export it, or use provider=mock."
        )
    return key


def choose_mock(
    candidates: list[Candidate], *, prefer: str | None = None
) -> tuple[str, float, dict[str, float]]:
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
    """Ask TypeSafe Jev (Choice) to pick exactly one candidate id for Aside."""
    from typesafe_sdk import Choice, TypeSafeClient

    if not candidates:
        raise ValueError("candidates must not be empty")

    key = _resolve_api_key(api_key)
    state: dict[str, Any] = {
        "goal": goal,
        "observation": observation,
        "history": history or [],
        "rule": (
            "Return only one of the supplied candidate IDs. "
            "Never invent tools, selectors, or arguments."
        ),
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
        response = client.system_one(
            state=state,
            questions=questions,
            model=model or DEFAULT_MODEL,
        )

    answer = (response.choices or response.answers)["aside_action"]
    choice = str(answer.choice)
    validate_choice(choice, candidates)
    confidence = float(answer.confidence or 0.0)
    probs = {str(k): float(v) for k, v in dict(answer.probabilities or {}).items()}
    for c in candidates:
        probs.setdefault(c.id, 0.0)
    return choice, confidence, probs


def system_one(
    state: Any,
    questions: dict[str, Any],
    *,
    model: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Call TypeSafe Jev System One with Choice / Score / Noul questions.

    ``questions`` values are either already-built SDK objects, or dicts shaped like:
      {"type":"choice","instructions":"...","criteria":{id: desc, ...}}
      {"type":"score","instructions":"...","criteria":["low","mid","high"]}
      {"type":"noul","instructions":"..."}
    """
    from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

    key = _resolve_api_key(api_key)
    built: dict[str, Any] = {}
    for name, q in questions.items():
        if hasattr(q, "instructions") or hasattr(q, "criteria"):
            # already a SDK question object
            built[name] = q
            continue
        if not isinstance(q, dict):
            raise TypeError(f"question {name!r} must be a dict or SDK question")
        qtype = str(q.get("type") or q.get("kind") or "").lower()
        instructions = q.get("instructions")
        criteria = q.get("criteria")
        if qtype in ("choice", "choose"):
            if not isinstance(criteria, dict) or not criteria:
                raise ValueError(f"choice {name!r} needs non-empty criteria map")
            built[name] = Choice(instructions=instructions, criteria=criteria)
        elif qtype == "score":
            if not isinstance(criteria, (list, tuple)) or len(criteria) < 2:
                raise ValueError(f"score {name!r} needs ordered criteria list (2+)")
            built[name] = Score(instructions=instructions, criteria=list(criteria))
        elif qtype in ("noul", "boolean", "bool"):
            built[name] = Noul(instructions=instructions, criteria=criteria)
        else:
            raise ValueError(
                f"question {name!r}: type must be choice|score|noul, got {qtype!r}"
            )

    with TypeSafeClient(api_key=key) as client:
        response = client.system_one(
            state=state,
            questions=built,
            model=model or DEFAULT_MODEL,
        )

    out: dict[str, Any] = {
        "model": response.model,
        "answers": {},
        "usage": None,
    }
    if response.usage is not None:
        u = response.usage
        out["usage"] = {
            "input_tokens": getattr(u, "input_tokens", None),
            "output_tokens": getattr(u, "output_tokens", None),
        }

    for name, ans in dict(response.answers or {}).items():
        entry: dict[str, Any] = {"name": name}
        if hasattr(ans, "choice"):
            entry.update(
                {
                    "type": "choice",
                    "choice": ans.choice,
                    "probabilities": dict(ans.probabilities or {}),
                    "confidence": float(ans.confidence or 0.0),
                }
            )
        elif hasattr(ans, "score"):
            entry.update(
                {
                    "type": "score",
                    "score": float(ans.score),
                    "probabilities": dict(getattr(ans, "probabilities", None) or {}),
                    "confidence": float(getattr(ans, "confidence", 0.0) or 0.0),
                }
            )
        elif hasattr(ans, "noul"):
            entry.update({"type": "noul", "noul": float(ans.noul)})
        else:
            entry["raw"] = str(ans)
        out["answers"][name] = entry
    return out
