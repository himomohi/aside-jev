from __future__ import annotations

import json
import os
import math
import re
import shutil
import subprocess
from typing import Any

MAX_OBSERVATION_CHARS = 12000
MAX_HISTORY_ITEMS = 12
MAX_HISTORY_CHARS = 8000
_SECRET_KEYS = ("password", "passwd", "token", "secret", "authorization", "cookie", "apikey", "credential", "privatekey")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:password|passwd|[\w-]*token|[\w-]*secret|api[_-]?key|authorization|cookie)\b\s*[=:]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s&,;]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_URL_CREDENTIAL = re.compile(r"(https?://)[^\s/@:]+:[^\s/@]+@", re.IGNORECASE)


def _redact_text(value: str) -> str:
    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _URL_CREDENTIAL.sub(r"\1[REDACTED]@", value)
    return _SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", value)


def sanitize_context(payload: Any, *, max_chars: int = MAX_OBSERVATION_CHARS) -> Any:
    """구조, 깊이, 문자열, 전체 JSON 크기를 제한하고 자격증명 필드를 가린다.

    자유 텍스트의 임의 비밀값까지 식별하는 DLP 기능은 아니다.
    """
    remaining = max_chars

    def text_value(value: str, limit: int = 2000) -> str:
        nonlocal remaining
        value = _redact_text(value[:max_chars])
        if len(value) > limit:
            value = value[:limit - 1] + "…"
        available = max(2, remaining)
        low, high = 0, len(value)
        while low < high:
            middle = (low + high + 1) // 2
            if len(json.dumps(value[:middle], ensure_ascii=False)) <= available:
                low = middle
            else:
                high = middle - 1
        result = value[:low]
        remaining -= len(json.dumps(result, ensure_ascii=False))
        return result

    def walk(value: Any, depth: int = 0) -> Any:
        nonlocal remaining
        if depth >= 6:
            return text_value("[TRUNCATED]")
        if isinstance(value, str):
            return text_value(value)
        if isinstance(value, dict):
            remaining -= 2
            out: dict[str, Any] = {}
            for index, (key, item) in enumerate(value.items()):
                if index >= 40 or remaining < 64:
                    break
                if not isinstance(key, str):
                    raise ValueError("context object keys must be strings")
                safe_key = text_value(key, limit=128)
                remaining -= 2
                normalized = re.sub(r"[^a-z0-9]", "", key.lower())
                out[safe_key] = text_value("[REDACTED]") if any(secret in normalized for secret in _SECRET_KEYS) else walk(item, depth + 1)
            return out
        if isinstance(value, (list, tuple)):
            remaining -= 2
            result = []
            for index, item in enumerate(value):
                if index >= 40 or remaining < 32:
                    break
                remaining -= 1
                result.append(walk(item, depth + 1))
            return result
        if value is None or isinstance(value, (bool, int, float)):
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("context must contain finite JSON values")
            try:
                encoded = json.dumps(value, allow_nan=False)
            except (ValueError, OverflowError):
                raise ValueError("context must contain finite JSON values") from None
            if len(encoded) > remaining:
                return text_value("[TRUNCATED]")
            remaining -= len(encoded)
            return value
        raise ValueError("context must contain JSON values")

    if isinstance(payload, str):
        return text_value(payload, limit=max_chars)
    result = walk(payload)
    if len(json.dumps(result, ensure_ascii=False, separators=(",", ":"))) > max_chars:
        return "[TRUNCATED]"
    return result


def summarize_history(history: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if history is None:
        return []
    if not isinstance(history, list) or any(not isinstance(item, dict) for item in history):
        raise ValueError("history must be an array of objects")
    # 전체 크기 제한에 도달해도 가장 최근 단계부터 보존한다.
    recent = sanitize_context(list(reversed(history[-MAX_HISTORY_ITEMS:])), max_chars=MAX_HISTORY_CHARS)
    return list(reversed(recent))


def resolve_aside_bin() -> str:
    env = os.environ.get("ASIDE_BIN")
    if env and os.path.isfile(env) and os.access(env, os.X_OK):
        return env
    found = shutil.which("aside")
    if found:
        return found
    raise FileNotFoundError(
        "aside CLI not found on PATH. Install Aside CLI or set ASIDE_BIN."
    )


def aside_repl(expression: str, *, timeout: float = 120.0) -> str:
    """Run one Aside REPL expression and return stdout text."""
    bin_path = resolve_aside_bin()
    proc = subprocess.run(
        [bin_path, "repl", expression],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"aside repl failed ({proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout.strip()


def aside_mcp_command() -> list[str]:
    return [resolve_aside_bin(), "mcp"]


def summarize_observation(payload: dict[str, Any] | str) -> dict[str, Any] | str:
    """Jev로 보내는 관측을 재귀 가림 처리하고 크기를 제한한다."""
    if not isinstance(payload, (dict, str)):
        raise ValueError("observation must be an object or string")
    return sanitize_context(payload)
