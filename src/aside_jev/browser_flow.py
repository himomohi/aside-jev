"""REPL 관찰 → 정제 → Jev 선택 → 고정 실행 → 관찰을 예산 안에서 반복한다."""
from __future__ import annotations

import asyncio
from collections import Counter
import hashlib
import re
from time import monotonic
from typing import Any, Callable

from .aside_bridge import sanitize_context
from .browser_policy import ActionRule as ActionRule, validate_completion
from .browser_runtime import AsideRuntime, BrowserRuntimeError, Observation, REF
from .core import parse_candidates, validate_confidence
from .jev import JevProviderError, choose_live, prepare_decision_context, resolve_timeout

ELEMENT = re.compile(r'^\s*-\s+(?P<role>link|button|textbox|searchbox|checkbox|radio|tab|combobox)\s+"(?P<name>(?:\\.|[^"\\])*)".*?\[ref=(?P<ref>(?:f\d+)?e\d+)\]')
MAX_ACTIONS = 24


def action_table(observation: Observation, rules: list[ActionRule]) -> list[dict[str, Any]]:
    elements = []
    for line in observation.tree.splitlines():
        match = ELEMENT.match(line)
        if not match or "[disabled]" in line:
            continue
        name = match["name"].replace('\\"', '"').replace("\\\\", "\\")
        elements.append((match["role"], name, line))
    counts = Counter((role, name) for role, name, _ in elements)
    rows = []
    for rule_index, rule in enumerate(rules):
        if counts[(rule.role, rule.name)] != 1:
            continue
        line = next(line for role, name, line in elements if (role, name) == (rule.role, rule.name))
        rows.append({
            "id": f"action-{rule_index}",
            "description": f"{rule.action} {rule.role} {rule.name}" + (f" with value {rule.value}" if rule.action == "fill" else ""),
            "tool": rule.action,
            "arguments": {"action": rule.action, "role": rule.role, "name": rule.name,
                          "line": REF.sub("[ref]", line), **({"value": rule.value} if rule.value is not None else {})},
        })
    return rows


def compact_observation(observation: Observation, *, goal: str, rules: list[ActionRule], completion_text: str) -> dict[str, Any]:
    # 전체 관찰은 로컬 검증에 남기고 모델에는 목표/허용 대상과 관련된 줄부터 보낸다.
    terms = {term.casefold() for term in re.findall(r"[\w가-힣]{2,}", goal + " " + completion_text)}
    names = {rule.name.casefold() for rule in rules}
    lines = observation.tree.splitlines()
    ranked = sorted(enumerate(lines), key=lambda pair: (
        -int(any(name in pair[1].casefold() for name in names)) * 100
        -sum(term in pair[1].casefold() for term in terms), pair[0]))
    selected: list[tuple[int, str]] = []
    budget = 4800
    for index, line in ranked:
        clean = REF.sub("[ref]", line)
        if len(clean) > 800:
            continue
        if len(clean) + 1 > budget or len(selected) >= 32:
            continue
        selected.append((index, clean))
        budget -= len(clean) + 1
    safe = sanitize_context({"url": observation.url, "page_lines": [line for _, line in sorted(selected)]}, max_chars=6400)
    if not isinstance(safe, dict):
        safe = {"page_lines": []}
    safe["total_lines"] = len(lines)
    safe["omitted_lines"] = len(lines) - len(safe.get("page_lines", []))
    return safe


def _fingerprint(observation: Observation) -> str:
    return hashlib.sha256(observation.identity.encode()).hexdigest()


def live_decision(**kwargs: Any) -> tuple[str, float, dict[str, float]]:
    return choose_live(**kwargs)


async def run_browser_flow(
    runtime: AsideRuntime, *, goal: str, target_id: str, action_rules: list[dict[str, Any]],
    completion_text: str, completion_url: str | None = None, max_steps: int = 12,
    total_timeout_s: float = 90, timeout_s: float = 15, min_confidence: float = .7,
    model: str = "jev-latest", policy_check: Callable[[], Any] = lambda: None,
    decision: Callable[..., tuple[str, float, dict[str, float]]] = live_decision,
) -> dict[str, Any]:
    prepare_decision_context(goal, {}, [])
    if not isinstance(target_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", target_id):
        raise ValueError("target_id must identify an existing Aside tab")
    if not isinstance(action_rules, list) or not 1 <= len(action_rules) <= MAX_ACTIONS:
        raise ValueError("Provide 1..24 explicitly authorized action rules")
    rules = [ActionRule.parse(item) for item in action_rules]
    if len(set(rules)) != len(rules):
        raise ValueError("Duplicate action rules are not allowed")
    validate_completion(completion_text, completion_url)
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or not 1 <= max_steps <= 30:
        raise ValueError("max_steps must be 1..30")
    timeout_s = resolve_timeout(timeout_s)
    validate_confidence(min_confidence, name="min_confidence")
    if isinstance(total_timeout_s, bool) or not isinstance(total_timeout_s, (float, int)) or not 1 <= total_timeout_s <= 300:
        raise ValueError("total_timeout_s must be 1..300")
    started = monotonic()
    history: list[dict[str, Any]] = []
    seen: Counter[str] = Counter()
    actions: set[tuple[str, str]] = set()

    def result(status: str, *, error: str | None = None) -> dict[str, Any]:
        return {"status": status, "verified": status == "verified", "steps": history,
                "elapsed_ms": round((monotonic() - started) * 1000, 3),
                "provider": "live", "model": model, "error": error,
                "retry": "manual", "automatic_fallback": False}

    async def check_policy() -> None:
        nonlocal min_confidence
        policy = await asyncio.to_thread(policy_check)
        if policy is not None:
            min_confidence = max(min_confidence, validate_confidence(policy["min_confidence"], name="min_confidence"))

    try:
        async with asyncio.timeout(total_timeout_s):
            await check_policy()
            observation = await runtime.attach(target_id)
            for step in range(max_steps):
                await check_policy()
                identity = _fingerprint(observation)
                seen[identity] += 1
                if seen[identity] >= 3:
                    return result("loop_detected")
                rows = action_table(observation, rules)
                success = completion_text in observation.tree and (completion_url is None or observation.url == completion_url)
                if success:
                    rows.append({"id": "finish", "description": "The explicit completion condition is visible. Finish the task.", "tool": None})
                if not rows:
                    return result("needs_input", error="현재 화면에 허용된 고유한 행동 대상이 없습니다.")
                descriptions = [sanitize_context(row["description"], max_chars=2000) for row in rows]
                if len(set(descriptions)) != len(descriptions):
                    return result("needs_input", error="정제 후 구별되지 않는 행동 후보가 있습니다. 규칙을 좁혀 주세요.")
                candidates = parse_candidates(rows)
                state = compact_observation(observation, goal=goal, rules=rules, completion_text=completion_text)
                state["completion"] = {"text": completion_text, "exact_url": completion_url, "observed": success}
                decision_started = monotonic()
                choice_id, confidence, _ = await asyncio.to_thread(
                    decision, candidates=candidates, goal=goal, observation=state,
                    history=history[-6:], model=model, timeout_s=timeout_s,
                )
                confidence = validate_confidence(confidence)
                selected = next((row for row in candidates if row.id == choice_id), None)
                if selected is None:
                    return result("invalid_choice")
                await check_policy()
                entry = {"step": step + 1, "choice_id": choice_id, "confidence": confidence,
                         "decision_ms": round((monotonic() - decision_started) * 1000, 3),
                         "executed": False, "execution_state": "not_started", "omitted_lines": state["omitted_lines"]}
                history.append(entry)
                if choice_id == "abstain" or confidence < min_confidence:
                    return result("abstained")
                if choice_id == "finish":
                    # 판단 중 외부에서 페이지가 바뀌었다면 완료를 확정하지 않는다.
                    confirmed = await runtime.attach(target_id)
                    if confirmed.identity != observation.identity:
                        return result("stale_observation")
                    return result("verified")
                signature = (identity, choice_id)
                if signature in actions:
                    return result("loop_detected")
                actions.add(signature)
                remaining_ms = max(1, min(10000, int((total_timeout_s - (monotonic() - started)) * 1000)))
                entry["execution_state"] = "unconfirmed"
                after = await runtime.execute(selected.arguments, observation, timeout_ms=remaining_ms)
                if after is None:
                    entry["execution_state"] = "not_started"
                    return result("stale_observation")
                entry["executed"] = True
                entry["execution_state"] = "confirmed"
                entry["page_changed"] = after.identity != observation.identity
                if not entry["page_changed"]:
                    return result("no_progress")
                observation = after
            return result("step_budget")
    except TimeoutError:
        return result("time_budget", error="시간 예산을 초과했습니다. 진행 중이던 브라우저 행동은 화면에서 확인해 주세요.")
    except JevProviderError as error:
        return result("provider_error", error=error.code)
    except BrowserRuntimeError:
        return result("execution_uncertain", error="브라우저 응답을 확인할 수 없습니다. 자동 재시도 없이 중단했습니다.")
    except RuntimeError:
        return result("stopped", error="Jev 연결 또는 ON 상태를 확인할 수 없어 중단했습니다.")
