"""확장 전용 MCP에만 적용되는 Jev 실행 정책."""
from __future__ import annotations

import os
from typing import Any


def active_policy() -> dict[str, Any] | None:
    if os.environ.get("ASIDE_JEV_EXTENSION_MODE") != "1":
        return None
    from .extension_control import load_key_environment, load_runtime_policy

    policy = load_runtime_policy()
    if not policy["enabled"]:
        raise RuntimeError("Aside Jev is OFF. Enable it from the extension popup before requesting a browser decision.")
    if not policy.get("execution_ready", False):
        raise RuntimeError("Jev connection is not verified. Run the popup ON connection check before proceeding.")
    if not load_key_environment():
        raise RuntimeError("Jev API key is not configured. Stop this browser task; do not use mock or another decision model.")
    return policy


def decision_options(
    *, provider: str, model: str | None, timeout_s: float | None,
    min_confidence: float = 0.0,
) -> dict[str, Any]:
    policy = active_policy()
    if policy is None:
        return {"provider": provider, "model": model, "timeout_s": timeout_s, "min_confidence": min_confidence}
    if provider != "live":
        raise ValueError("The enabled browser extension requires live Jev decisions. Mock fallback is not allowed.")
    from .core import validate_confidence

    threshold = max(validate_confidence(min_confidence, name="min_confidence"), policy["min_confidence"])
    return {"provider": "live", "model": policy["model"], "timeout_s": policy["timeout_s"], "min_confidence": threshold}
