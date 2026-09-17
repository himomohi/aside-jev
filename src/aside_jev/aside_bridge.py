from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any


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
    """Keep Jev prompts small — strip secrets-looking fields."""
    if isinstance(payload, str):
        return payload[:4000]
    redacted = {}
    for key, value in payload.items():
        lk = key.lower()
        if any(s in lk for s in ("password", "token", "secret", "authorization", "cookie")):
            redacted[key] = "[REDACTED]"
        else:
            redacted[key] = value
    return redacted
