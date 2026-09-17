from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .aside_bridge import summarize_observation
from .core import Candidate, build_abstain, validate_choice
from .jev import system_one
from .loop import decide

mcp = FastMCP(
    "aside-jev",
    instructions=(
        "TypeSafe Jev (System One) for Aside agents. "
        "Jev is a decision-only model: Choice / Score / Noul — no text generation. "
        "Use jev_system_one for general decisions; use jev_choose/jev_step when the "
        "app owns a candidate action table and Aside will execute the chosen id. "
        "Never invent tools, selectors, or arguments outside the supplied table."
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
def jev_system_one(
    state: dict[str, Any] | str | list[Any],
    questions: dict[str, Any],
    model: str | None = "jev-latest",
) -> dict[str, Any]:
    """Call TypeSafe Jev System One (Choice / Score / Noul) on shared state.

    questions example:
      {
        "next": {"type":"choice","instructions":"Next step","criteria":{"a":"...","b":"..."}},
        "done": {"type":"noul","instructions":"The task is complete"},
        "risk": {"type":"score","instructions":"How risky","criteria":["low","medium","high"]}
      }
    """
    return system_one(state, questions, model=model)


@mcp.tool()
def jev_choose(
    goal: str,
    observation: dict[str, Any] | str,
    candidates: list[dict[str, Any]],
    provider: str = "live",
    history: list[dict[str, Any]] | None = None,
    model: str | None = "jev-latest",
    prefer: str | None = None,
) -> dict[str, Any]:
    """Jev Choice over an app-owned candidate table (for Aside to execute)."""
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
        "model": None if prov == "mock" else (model or "jev-latest"),
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
    model: str | None = "jev-latest",
    min_confidence: float = 0.0,
) -> dict[str, Any]:
    """One Jev decision step for Aside: choose + validate + execute payload."""
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
            "model": result.get("model"),
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
