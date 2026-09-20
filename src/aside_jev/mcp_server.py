from __future__ import annotations

import asyncio
import json
import threading
from time import perf_counter
from typing import Any

from mcp.server.fastmcp import FastMCP

from .aside_bridge import MAX_HISTORY_ITEMS, MAX_OBSERVATION_CHARS
from .core import parse_candidates, validate_choice, validate_confidence
from .jev import close_clients, prepare_decision_context, resolve_timeout, system_one
from .loop import decide
from .extension_gate import active_policy, decision_options

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

_browser_lock = threading.Lock()

_parse_candidates = parse_candidates


def jev_system_one(
    state: dict[str, Any] | str | list[Any],
    questions: dict[str, Any],
    model: str | None = "jev-latest",
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """Call Jev System One (Choice / Score / Noul) on bounded shared state."""
    started = perf_counter()
    result = system_one(state, questions, model=model, timeout_s=timeout_s)
    result["timing_ms"] = {"total": round((perf_counter() - started) * 1000, 3)}
    return result


def jev_choose(
    goal: str,
    observation: dict[str, Any] | str,
    candidates: list[dict[str, Any]],
    provider: str = "live",
    history: list[dict[str, Any]] | None = None,
    model: str | None = "jev-latest",
    prefer: str | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """Jev Choice over an app-owned candidate table (for Aside to execute)."""
    started = perf_counter()
    if provider not in ("mock", "live"):
        raise ValueError("provider must be mock or live")
    timeout = resolve_timeout(timeout_s)
    parsed = parse_candidates(candidates)
    safe_goal, obs, safe_history = prepare_decision_context(goal, observation, history)
    prepared = perf_counter()
    candidate, confidence, probabilities = decide(
        parsed,
        goal=safe_goal,
        observation=obs,
        provider=provider,
        history=safe_history,
        model=model,
        prefer=prefer,
        timeout_s=timeout,
    )
    finished = perf_counter()
    return {
        "choice_id": candidate.id,
        "confidence": confidence,
        "probabilities": probabilities,
        "candidate": candidate.to_dict(),
        "provider": provider,
        "model": None if provider == "mock" else (model or "jev-latest"),
        "timing_ms": {
            "preparation": round((prepared - started) * 1000, 3),
            "decision": round((finished - prepared) * 1000, 3),
            "total": round((finished - started) * 1000, 3),
        },
        "context": {
            "observation_chars": len(json.dumps(obs, ensure_ascii=False)),
            "history_items": len(safe_history),
            "history_dropped": max(0, len(history or []) - len(safe_history)),
            "observation_limit": MAX_OBSERVATION_CHARS,
            "history_limit": MAX_HISTORY_ITEMS,
        },
        "request_policy": {"timeout_s": timeout, "max_retries": 0, "result_cache": False},
    }


def jev_validate(choice_id: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Fail closed if choice_id is not in the supplied candidate table."""
    parsed = parse_candidates(candidates)
    candidate = validate_choice(choice_id, parsed)
    return {"ok": True, "candidate": candidate.to_dict()}


def jev_step(
    goal: str,
    observation: dict[str, Any] | str,
    candidates: list[dict[str, Any]],
    provider: str = "live",
    history: list[dict[str, Any]] | None = None,
    model: str | None = "jev-latest",
    min_confidence: float = 0.0,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """Choose and validate one action; return a payload without executing it."""
    started = perf_counter()
    threshold = validate_confidence(min_confidence, name="min_confidence")
    result = jev_choose(
        goal=goal, observation=observation, candidates=candidates,
        provider=provider, history=history, model=model, timeout_s=timeout_s,
    )
    if result["confidence"] < threshold and result["choice_id"] != "abstain":
        abstain = next(candidate for candidate in parse_candidates(candidates) if candidate.id == "abstain")
        result.update({
            "suggested_choice_id": result["choice_id"],
            "choice_id": abstain.id,
            "candidate": abstain.to_dict(),
            "downgraded_to_abstain": True,
            "reason": f"confidence {result['confidence']} < min_confidence {threshold}",
        })
    result["execute"] = {
        "tool": result["candidate"].get("tool"),
        "arguments": result["candidate"].get("arguments") or {},
        "should_execute": result["choice_id"] != "abstain" and bool(result["candidate"].get("tool")),
    }
    result["timing_ms"]["total"] = round((perf_counter() - started) * 1000, 3)
    return result


# 공개 동기 함수는 CLI와 로컬 UI에서 사용하고 MCP 작업만 이벤트 루프 밖에서 실행한다.
@mcp.tool(name="jev_system_one")
async def _mcp_system_one(
    state: dict[str, Any] | str | list[Any], questions: dict[str, Any],
    model: str | None = "jev-latest", timeout_s: float | None = None,
) -> dict[str, Any]:
    """Call TypeSafe Jev System One with Choice / Score / Noul questions."""
    policy = await asyncio.to_thread(active_policy)
    if policy:
        model, timeout_s = policy["model"], policy["timeout_s"]
    result = await asyncio.to_thread(jev_system_one, state=state, questions=questions, model=model, timeout_s=timeout_s)
    await asyncio.to_thread(active_policy)
    return result


@mcp.tool(name="jev_choose")
async def _mcp_choose(
    goal: str, observation: dict[str, Any] | str, candidates: list[dict[str, Any]],
    provider: str = "live", history: list[dict[str, Any]] | None = None,
    model: str | None = "jev-latest", prefer: str | None = None, timeout_s: float | None = None,
) -> dict[str, Any]:
    """Choose an app-owned action ID. No action is executed by this tool."""
    policy = await asyncio.to_thread(active_policy)
    if policy:
        if prefer is not None:
            raise ValueError("Preferred mock choices are not allowed in extension mode.")
        options = decision_options(provider=provider, model=model, timeout_s=timeout_s)
        result = await asyncio.to_thread(jev_step, goal=goal, observation=observation, candidates=candidates, history=history, **options)
        latest = await asyncio.to_thread(active_policy)
        if latest and latest["min_confidence"] > options["min_confidence"]:
            raise RuntimeError("Jev confidence settings changed during this request. Request a fresh decision.")
        return result
    return await asyncio.to_thread(jev_choose, goal=goal, observation=observation, candidates=candidates, provider=provider, history=history, model=model, prefer=prefer, timeout_s=timeout_s)


@mcp.tool(name="jev_validate")
async def _mcp_validate(choice_id: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate a supplied candidate ID and return its original action payload."""
    return jev_validate(choice_id=choice_id, candidates=candidates)


@mcp.tool(name="jev_step")
async def _mcp_step(
    goal: str, observation: dict[str, Any] | str, candidates: list[dict[str, Any]],
    provider: str = "live", history: list[dict[str, Any]] | None = None,
    model: str | None = "jev-latest", min_confidence: float = 0.0,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """Choose, validate, and apply a confidence gate; return an execution payload."""
    options = await asyncio.to_thread(decision_options, provider=provider, model=model, timeout_s=timeout_s, min_confidence=min_confidence)
    result = await asyncio.to_thread(jev_step, goal=goal, observation=observation, candidates=candidates, history=history, **options)
    latest = await asyncio.to_thread(active_policy)
    if latest and latest["min_confidence"] > options["min_confidence"]:
        raise RuntimeError("Jev confidence settings changed during this request. Request a fresh decision.")
    return result


@mcp.tool(name="jev_extension_status")
async def _mcp_extension_status() -> dict[str, Any]:
    """Read the popup toggle state; this does not change settings or call Jev."""
    from .extension_control import get_status

    return await asyncio.to_thread(get_status)


@mcp.tool(name="jev_browser_run")
async def _mcp_browser_run(
    goal: str, target_id: str, action_rules: list[dict[str, Any]],
    completion_text: str, completion_url: str | None = None,
    max_steps: int = 12, total_timeout_s: float = 90,
    min_confidence: float = .7, timeout_s: float = 15,
) -> dict[str, Any]:
    """Run observe → Jev → execute in one persistent Aside REPL session.

    action_rules are explicitly authorized exact role/name/action rows; fill also
    requires an explicit value. Never include an action needing ungranted user
    approval. Supports click/focus/fill only. Uses live Jev, never a fallback LLM.
    A completion_text and optional exact completion_url verify success locally.
    Stops on stale observations, repeated actions/pages, errors and budgets.
    """
    from .browser_runtime import connect_aside
    from .browser_flow import run_browser_flow

    if not 1 <= total_timeout_s <= 300:
        raise ValueError("total_timeout_s must be 1..300")
    options = await asyncio.to_thread(decision_options, provider="live", model="jev-latest", timeout_s=timeout_s, min_confidence=min_confidence)
    options.pop("provider")
    if not _browser_lock.acquire(blocking=False):
        raise RuntimeError("Another Jev browser flow is already running. Wait for it to finish.")
    try:
        async with asyncio.timeout(total_timeout_s):
            async with connect_aside() as runtime:
                return await run_browser_flow(runtime, goal=goal, target_id=target_id, action_rules=action_rules,
                                              completion_text=completion_text, completion_url=completion_url,
                                              max_steps=max_steps, total_timeout_s=total_timeout_s,
                                              policy_check=active_policy, **options)
    except TimeoutError:
        return {"status": "time_budget", "verified": False, "automatic_fallback": False, "retry": "manual",
                "error": "Aside 연결 또는 작업 시간이 전체 예산을 초과했습니다. 진행 중이던 행동은 화면에서 확인해 주세요."}
    finally:
        _browser_lock.release()


def main() -> None:
    try:
        mcp.run(transport="stdio")
    finally:
        close_clients()


if __name__ == "__main__":
    main()
