from __future__ import annotations

import atexit
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
import os
import threading
from typing import Any, Iterator

from .aside_bridge import sanitize_context, summarize_history, summarize_observation
from .core import Candidate, criteria_map, validate_candidates, validate_choice, validate_confidence

DEFAULT_MODEL = "jev-latest"
DEFAULT_TIMEOUT_S = 15.0
MAX_IN_FLIGHT = 8


class JevConfigurationError(RuntimeError):
    code = "configuration"


class JevProviderError(RuntimeError):
    def __init__(self, message: str, *, code: str = "unavailable") -> None:
        super().__init__(message)
        self.code = code


class JevBusyError(RuntimeError):
    code = "busy"


def resolve_timeout(timeout_s: float | None = None) -> float:
    value = DEFAULT_TIMEOUT_S if timeout_s is None else timeout_s
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 1 <= value <= 60:
        raise ValueError("timeout_s must be a finite number between 1 and 60 seconds")
    return float(value)


def _resolve_api_key(api_key: str | None = None) -> str:
    key = api_key or os.environ.get("TYPESAFE_API_KEY") or os.environ.get("TYPESAFEAI_API_KEY")
    if not isinstance(key, str) or not key.strip():
        raise JevConfigurationError("TYPESAFE_API_KEY is required for live Jev. Configure the key on the server, or use provider=mock.")
    return key.strip()


@dataclass
class _ClientEntry:
    client: Any
    active: int = 0
    closing: bool = False


# HTTP 연결만 재사용한다. 결정 결과와 사용자 상태는 캐시하지 않는다.
_clients: OrderedDict[tuple[str, str], _ClientEntry] = OrderedDict()
_clients_lock = threading.Lock()
_request_slots = threading.BoundedSemaphore(MAX_IN_FLIGHT)


def _new_client(key: str, base_url: str | None) -> Any:
    from typesafe_sdk import RetryPolicy, TypeSafeClient

    # SDK 기본 재시도는 2회다. 모호하게 실패한 유료 요청의 재전송을 막는다.
    return TypeSafeClient(api_key=key, base_url=base_url, timeout=DEFAULT_TIMEOUT_S, retry=RetryPolicy(max_retries=0))


@contextmanager
def _client_lease(key: str) -> Iterator[Any]:
    base_url = os.environ.get("TYPESAFE_BASE_URL", "").strip() or None
    identity = (hashlib.sha256(key.encode()).hexdigest(), base_url or "")
    with _clients_lock:
        entry = _clients.get(identity)
        if entry is None or entry.closing:
            if len(_clients) >= 4:
                idle = next((item for item, cached in _clients.items() if cached.active == 0), None)
                if idle is None:
                    raise JevBusyError("Jev is busy. Wait for an active request to finish and retry.")
                _clients.pop(idle).client.close()
            try:
                entry = _ClientEntry(_new_client(key, base_url))
            except (ValueError, TypeError):
                raise JevConfigurationError("Jev client configuration is invalid. Check the server API endpoint and key configuration.") from None
            _clients[identity] = entry
        _clients.move_to_end(identity)
        entry.active += 1
    try:
        yield entry.client
    finally:
        with _clients_lock:
            entry.active -= 1
            if entry.closing and entry.active == 0:
                if _clients.get(identity) is entry:
                    _clients.pop(identity)
                entry.client.close()


def close_clients() -> None:
    """유휴 연결을 닫고 사용 중인 연결은 마지막 요청이 끝날 때 정리한다."""
    with _clients_lock:
        for identity, entry in list(_clients.items()):
            entry.closing = True
            if entry.active == 0:
                _clients.pop(identity)
                entry.client.close()


atexit.register(close_clients)


def _request(state: Any, questions: dict[str, Any], *, model: str | None, api_key: str | None, timeout_s: float | None) -> Any:
    from typesafe_sdk import TypeSafeAPIError, TypeSafeAPITimeoutError, TypeSafeAPIResponseValidationError, TypeSafeError

    timeout = resolve_timeout(timeout_s)
    if model is not None and (not isinstance(model, str) or not model.strip() or len(model) > 128):
        raise ValueError("model must be a non-empty string of at most 128 characters")
    key = _resolve_api_key(api_key)
    if not _request_slots.acquire(blocking=False):
        raise JevBusyError("Jev is busy. Wait for an active request to finish and retry.")
    try:
        with _client_lease(key) as client:
            return client.system_one(state=state, questions=questions, model=model or DEFAULT_MODEL, timeout=timeout)
    except TypeSafeAPITimeoutError:
        raise JevProviderError("Jev exceeded the HTTP timeout. The request was not automatically retried; check the connection before retrying.", code="timeout") from None
    except TypeSafeAPIResponseValidationError:
        raise JevProviderError("Jev returned invalid response data. No action was selected.", code="invalid_response") from None
    except TypeSafeAPIError as error:
        if error.status in (401, 403):
            raise JevProviderError("Jev authentication failed. Check the server API key and model access.", code="authentication") from None
        if error.status == 429:
            raise JevProviderError("Jev rate limit reached. Wait before retrying.", code="rate_limit") from None
        if error.status in (400, 404, 422):
            raise JevProviderError("Jev rejected the request. Check the model and question schema.", code="invalid_request") from None
        raise JevProviderError("Jev could not complete the request. No action was selected; retry after checking provider status.") from None
    except TypeSafeError:
        raise JevProviderError("Jev could not connect or returned invalid data. Check the server endpoint and network.") from None
    finally:
        _request_slots.release()


def prepare_decision_context(goal: str, observation: dict[str, Any] | str, history: list[dict[str, Any]] | None) -> tuple[str, dict[str, Any] | str, list[dict[str, Any]]]:
    if not isinstance(goal, str) or not goal.strip() or len(goal) > 4000:
        raise ValueError("goal must contain 1 to 4000 characters")
    return sanitize_context(goal, max_chars=4000), summarize_observation(observation), summarize_history(history)


def choose_mock(candidates: list[Candidate], *, prefer: str | None = None) -> tuple[str, float, dict[str, float]]:
    """Deterministic chooser for credential-free CI and demos."""
    validate_candidates(candidates)
    ids = [c.id for c in candidates]
    if prefer is not None and prefer not in ids:
        raise ValueError("preferred candidate is not in the supplied table")
    selected = prefer if prefer is not None else next((i for i in ids if i != "abstain"), ids[0])
    probs = {i: (1.0 if i == selected else 0.0) for i in ids}
    return selected, probs[selected], probs


def choose_live(
    candidates: list[Candidate],
    *,
    goal: str,
    observation: dict[str, Any] | str,
    history: list[dict[str, Any]] | None = None,
    model: str | None = None,
    api_key: str | None = None,
    timeout_s: float | None = None,
) -> tuple[str, float, dict[str, float]]:
    """Ask TypeSafe Jev to select a supplied action, using a pooled connection."""
    from typesafe_sdk import Choice

    validate_candidates(candidates)
    goal, observation, history = prepare_decision_context(goal, observation, history)
    state = {
        "goal": goal,
        "observation": observation,
        "history": history,
        "rule": "Return only one of the supplied candidate IDs. Never invent tools, selectors, or arguments.",
    }
    questions = {"aside_action": Choice(
        instructions="Which complete executable action should the Aside agent run next? Pick exactly one candidate id from the criteria.",
        criteria={key: sanitize_context(value, max_chars=2000) for key, value in criteria_map(candidates).items()},
    )}
    response = _request(state, questions, model=model, api_key=api_key, timeout_s=timeout_s)
    try:
        answer = (response.choices or response.answers)["aside_action"]
        choice = answer.choice
        validate_choice(choice, candidates)
        confidence = validate_confidence(answer.confidence)
        raw_probs = dict(answer.probabilities or {})
        if any(key not in {candidate.id for candidate in candidates} for key in raw_probs):
            raise ValueError("unknown probability key")
        probs = {str(key): validate_confidence(value, name="probability") for key, value in raw_probs.items()}
        for candidate in candidates:
            probs.setdefault(candidate.id, 0.0)
    except (AttributeError, KeyError, TypeError, ValueError):
        raise JevProviderError("Jev returned an invalid action or confidence. No action was selected.", code="invalid_response") from None
    return choice, confidence, probs


def system_one(
    state: Any,
    questions: dict[str, Any],
    *,
    model: str | None = None,
    api_key: str | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """Call Jev with Choice / Score / Noul questions and bounded shared state."""
    from typesafe_sdk import Choice, Noul, Score

    if not isinstance(state, (str, dict, list)):
        raise ValueError("state must be text, an object, or an array")
    resolve_timeout(timeout_s)
    if not isinstance(questions, dict) or not 1 <= len(questions) <= 32:
        raise ValueError("questions must contain 1 to 32 named questions")
    built: dict[str, Any] = {}
    for name, question in questions.items():
        if not isinstance(name, str) or not name.strip() or len(name) > 128:
            raise ValueError("question names must contain 1 to 128 characters")
        if isinstance(question, (Choice, Score, Noul)):
            question = {"type": "choice" if isinstance(question, Choice) else "score" if isinstance(question, Score) else "noul", "instructions": question.instructions, "criteria": question.criteria}
        if not isinstance(question, dict):
            raise ValueError("each question must be a dict or SDK question")
        if set(question) - {"type", "kind", "instructions", "criteria"}:
            raise ValueError("Use instructions (not question/rubric). Score needs an ordered criteria array; Noul needs true/false criteria or instructions.")
        qtype = str(question.get("type") or question.get("kind") or "").lower()
        instructions = question.get("instructions")
        if instructions is not None and not isinstance(instructions, (str, dict, list)):
            raise ValueError("question instructions must be text, an object, or an array")
        instructions = sanitize_context(instructions, max_chars=4000) if instructions else instructions
        criteria = question.get("criteria")
        if qtype in ("choice", "choose"):
            if not isinstance(criteria, dict) or not 1 <= len(criteria) <= 64:
                raise ValueError("choice questions need 1 to 64 criteria")
            if any(not isinstance(key, str) or not key.strip() or len(key) > 128 or (value is not None and not isinstance(value, (str, dict, list))) for key, value in criteria.items()):
                raise ValueError("choice criteria require string IDs and text, object, array, or null descriptions")
            built[name] = Choice(instructions=instructions, criteria={key: sanitize_context(value, max_chars=2000) for key, value in criteria.items()})
        elif qtype == "score":
            if not isinstance(criteria, (list, tuple)) or not 2 <= len(criteria) <= 64 or any(not isinstance(item, (str, dict, list)) for item in criteria):
                raise ValueError("score questions need 2 to 64 ordered text, object, or array criteria")
            built[name] = Score(instructions=instructions, criteria=[sanitize_context(item, max_chars=2000) for item in criteria])
        elif qtype in ("noul", "boolean", "bool"):
            if not instructions and not criteria:
                raise ValueError("noul needs instructions or true/false criteria")
            if criteria is not None and (not isinstance(criteria, dict) or set(criteria) - {"true", "false"}):
                raise ValueError("noul criteria must be an object with true/false descriptions or null")
            built[name] = Noul(instructions=instructions, criteria=sanitize_context(criteria, max_chars=2000))
        else:
            raise ValueError("question type must be choice, score, or noul")

    question_chars = sum(len(json.dumps({"instructions": question.instructions, "criteria": question.criteria}, ensure_ascii=False)) for question in built.values())
    if question_chars > 64000:
        raise ValueError("questions exceed the 64000-character context limit")

    response = _request(sanitize_context(state, max_chars=24000), built, model=model, api_key=api_key, timeout_s=timeout_s)
    out: dict[str, Any] = {"model": response.model, "answers": {}, "usage": None}
    if response.usage is not None:
        out["usage"] = {"input_tokens": getattr(response.usage, "input_tokens", None), "output_tokens": getattr(response.usage, "output_tokens", None)}
    try:
        if set(response.answers or {}) != set(built):
            raise ValueError("missing answer")
        for name, answer in dict(response.answers or {}).items():
            entry: dict[str, Any] = {"name": name}
            if hasattr(answer, "choice"):
                if not isinstance(built[name], Choice) or answer.choice not in built[name].criteria:
                    raise ValueError("unknown choice")
                if set(answer.probabilities or {}) - set(built[name].criteria):
                    raise ValueError("unknown choice probability")
                entry.update({"type": "choice", "choice": answer.choice, "probabilities": {key: validate_confidence(value) for key, value in dict(answer.probabilities or {}).items()}, "confidence": validate_confidence(answer.confidence)})
            elif hasattr(answer, "score"):
                if not isinstance(built[name], Score):
                    raise ValueError("unexpected score answer")
                score = answer.score
                if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= len(built[name].criteria) - 1:
                    raise ValueError("invalid score")
                entry.update({"type": "score", "score": float(score), "probabilities": {key: validate_confidence(value) for key, value in dict(getattr(answer, "probabilities", None) or {}).items()}, "confidence": validate_confidence(getattr(answer, "confidence", None))})
            elif hasattr(answer, "noul"):
                if not isinstance(built[name], Noul):
                    raise ValueError("unexpected noul answer")
                entry.update({"type": "noul", "noul": validate_confidence(answer.noul, name="noul")})
            else:
                raise ValueError("unknown answer type")
            out["answers"][name] = entry
    except (AttributeError, KeyError, TypeError, ValueError):
        raise JevProviderError("Jev returned incomplete or invalid answers. No result is available.", code="invalid_response") from None
    return out
