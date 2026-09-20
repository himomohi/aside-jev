from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
from typing import Any, Literal

Outcome = Literal["verified", "refuted", "unknown", "abstained", "budget_exhausted"]
MAX_CANDIDATES = 64


@dataclass(frozen=True)
class Candidate:
    """One executable action owned by the application — never invented by Jev."""

    id: str
    description: str
    tool: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_abstain(reason: str = "No safe executable action for the current observation.") -> Candidate:
    return Candidate(id="abstain", description=reason, tool=None, arguments={})


def validate_choice(choice: str, candidates: list[Candidate]) -> Candidate:
    validate_candidates(candidates)
    for candidate in candidates:
        if candidate.id == choice:
            return candidate
    known = ", ".join(sorted(c.id for c in candidates)) or "(none)"
    raise ValueError(f"provider selected unknown candidate {choice!r}; known={known}")


def criteria_map(candidates: list[Candidate]) -> dict[str, str]:
    validate_candidates(candidates)
    return {c.id: c.description for c in candidates}


def validate_candidates(candidates: list[Candidate]) -> None:
    """실행 표의 중복이나 모호한 abstain을 API 호출 전에 거부한다."""
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise ValueError(f"candidates must contain 1 to {MAX_CANDIDATES} actions")
    seen: set[str] = set()
    criteria_chars = 0
    for candidate in candidates:
        if not isinstance(candidate, Candidate):
            raise ValueError("each candidate must be a Candidate")
        if not isinstance(candidate.id, str) or not candidate.id.strip() or len(candidate.id) > 128:
            raise ValueError("candidate id must be a non-empty string of at most 128 characters")
        if candidate.id in seen:
            raise ValueError("candidate ids must be unique")
        seen.add(candidate.id)
        if not isinstance(candidate.description, str) or not candidate.description.strip() or len(candidate.description) > 2000:
            raise ValueError("candidate description must contain 1 to 2000 characters")
        criteria_chars += len(candidate.id) + len(candidate.description)
        if criteria_chars > 24000:
            raise ValueError("candidate descriptions exceed the 24000-character context limit")
        if candidate.tool is not None and (not isinstance(candidate.tool, str) or not candidate.tool.strip() or len(candidate.tool) > 256):
            raise ValueError("candidate tool must be null or a non-empty string of at most 256 characters")
        if not isinstance(candidate.arguments, dict):
            raise ValueError("candidate arguments must be a JSON object")
        try:
            encoded = json.dumps(candidate.arguments, allow_nan=False)
        except (TypeError, ValueError, RecursionError):
            raise ValueError("candidate arguments must contain finite JSON values") from None
        if len(encoded) > 16000:
            raise ValueError("candidate arguments exceed 16000 characters")
        if candidate.id == "abstain" and (candidate.tool is not None or candidate.arguments):
            raise ValueError("abstain must not contain a tool or arguments")


def parse_candidates(raw: list[dict[str, Any]], *, include_abstain: bool = True) -> list[Candidate]:
    if not isinstance(raw, list) or not raw or len(raw) > MAX_CANDIDATES:
        raise ValueError(f"candidates must contain 1 to {MAX_CANDIDATES} actions")
    out: list[Candidate] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each candidate must be an object")
        candidate_id = item.get("id")
        out.append(Candidate(
            id=candidate_id,
            description=item.get("description") or candidate_id,
            tool=item.get("tool"),
            arguments=item.get("arguments", {}),
        ))
    validate_candidates(out)
    if include_abstain and not any(c.id == "abstain" for c in out):
        if len(out) == MAX_CANDIDATES:
            raise ValueError(f"reserve one of {MAX_CANDIDATES} candidates for abstain")
        out.append(build_abstain())
    return out


def validate_confidence(value: float, *, name: str = "confidence") -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be a finite number between 0 and 1")
    return float(value)


def classify(submitted: str | None, expected: str, *, steps: int, max_steps: int) -> Outcome:
    if submitted == expected:
        return "verified"
    if submitted is not None:
        return "refuted"
    if steps >= max_steps:
        return "budget_exhausted"
    return "unknown"
