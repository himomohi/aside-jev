from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Outcome = Literal["verified", "refuted", "unknown", "abstained", "budget_exhausted"]


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
    for candidate in candidates:
        if candidate.id == choice:
            return candidate
    known = ", ".join(sorted(c.id for c in candidates)) or "(none)"
    raise ValueError(f"provider selected unknown candidate {choice!r}; known={known}")


def criteria_map(candidates: list[Candidate]) -> dict[str, str]:
    return {c.id: c.description for c in candidates}


def classify(submitted: str | None, expected: str, *, steps: int, max_steps: int) -> Outcome:
    if submitted == expected:
        return "verified"
    if submitted is not None:
        return "refuted"
    if steps >= max_steps:
        return "budget_exhausted"
    return "unknown"
