from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from .core import Candidate, build_abstain, validate_choice
from .loop import decide
from .aside_bridge import summarize_observation

mcp = FastMCP(
    "aside-jev",
    instructions=(
        "Bounded TypeSafe Jev chooser for Aside. "
        "The application owns the candidate table; Jev only returns one supplied id. "
        "Never invent tool names, selectors, or arguments."
    ),
)


def _parse_candidates(raw: list[dict[str, Any]]) -> list[Candidate]:
    out: list[Candidate] = []
    for item in raw:
        out.append(
            Candidate(
                id=str(item["id"]),
                description=str(item.get("description") or item["id"]),
                tool=item.get("tool"),
                arguments=dict(item.get("arguments") or {}),
            )
        )
    if not any(c.id == "abstain" for c in out):
        out.append(build_abstain())
    return out


@mcp.tool()
def jev_choose(
    goal: str,
    observation: dict[str, Any] | str,
    candidates: list[dict[str, Any]],
    provider: str = "live",
    history: list[dict[str, Any]] | None = None,
    model: str | None = None,
    prefer: str | None = None,
) -> dict[str, Any]:
    """Pick exactly one application-owned candidate id via mock or live TypeSafe Jev."""
    parsed = _parse_candidates(candidates)
    obs = summarize_observation(observation)
    prov = "mock" if provider == "mock" else "live"
    candidate, confidence, probs = decide(
        parsed,
        goal=goal,
        observation=obs,
        provider=prov,  # type: ignore[arg-type]
        history=history,
        model=model,
        prefer=prefer,
    )
    return {
        "choice_id": candidate.id,
        "confidence": confidence,
        "probabilities": probs,
        "candidate": candidate.to_dict(),
        "provider": prov,
    }


@mcp.tool()
def jev_validate(
    choice_id: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Fail closed if choice_id is not in the supplied candidate table."""
    parsed = _parse_candidates(candidates)
    candidate = validate_choice(choice_id, parsed)
    return {"ok": True, "candidate": candidate.to_dict()}


@mcp.tool()
def jev_step(
    goal: str,
    observation: dict[str, Any] | str,
    candidates: list[dict[str, Any]],
    provider: str = "live",
    history: list[dict[str, Any]] | None = None,
    model: str | None = None,
    min_confidence: float = 0.0,
) -> dict[str, Any]:
    """One bounded decision step: choose + validate, ready for Aside execution."""
    result = jev_choose(
        goal=goal,
        observation=observation,
        candidates=candidates,
        provider=provider,
        history=history,
        model=model,
    )
    if result["confidence"] < min_confidence and result["choice_id"] != "abstain":
        parsed = _parse_candidates(candidates)
        abstain = next(c for c in parsed if c.id == "abstain")
        result = {
            "choice_id": abstain.id,
            "confidence": result["confidence"],
            "probabilities": result["probabilities"],
            "candidate": abstain.to_dict(),
            "provider": result["provider"],
            "downgraded_to_abstain": True,
            "reason": f"confidence {result['confidence']} < min_confidence {min_confidence}",
        }
    result["execute"] = {
        "tool": result["candidate"].get("tool"),
        "arguments": result["candidate"].get("arguments") or {},
        "should_execute": bool(result["candidate"].get("tool")),
    }
    return result


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
