"""Validate browser action rules and completion signals before any side effects."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ActionRule:
    role: str
    name: str
    action: str
    value: str | None = None

    @classmethod
    def parse(cls, data: dict[str, Any]) -> "ActionRule":
        if not isinstance(data, dict) or set(data) - {"role", "name", "action", "value"}:
            raise ValueError("action_rules require role, exact name, action and optional value")
        try:
            rule = cls(**data)
        except TypeError:
            raise ValueError("action_rules require role, name and action") from None
        if rule.role not in ("link", "button", "textbox", "searchbox", "checkbox", "radio", "tab", "combobox"):
            raise ValueError("Unsupported action role")
        if not isinstance(rule.name, str) or not rule.name.strip() or not 1 <= len(rule.name) <= 300:
            raise ValueError("Each action rule needs a non-blank exact accessible name of 1..300 characters")
        if rule.action not in ("click", "focus", "fill"):
            raise ValueError("action must be click, focus, or fill")
        if rule.action == "fill":
            if rule.role not in ("textbox", "searchbox") or not isinstance(rule.value, str) or len(rule.value) > 1000:
                raise ValueError("fill requires a textbox/searchbox and an explicit value of up to 1000 characters")
        elif rule.value is not None:
            raise ValueError("Only fill actions accept a value")
        return rule


def validate_completion(completion_text: str, completion_url: str | None) -> None:
    """Require a meaningful signal; preserve the original text/URL for exact matching."""
    if (
        not isinstance(completion_text, str)
        or not 3 <= len(completion_text.strip())
        or len(completion_text) > 300
    ):
        raise ValueError("completion_text must contain 3..300 characters, with at least 3 after trimming whitespace")
    if completion_url is None:
        return
    error = "completion_url must be an exact HTTP(S) URL with a valid host and port, without whitespace"
    if (
        not isinstance(completion_url, str)
        or not 1 <= len(completion_url) <= 2000
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in completion_url)
    ):
        raise ValueError(error)
    try:
        parsed = urlsplit(completion_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError(error)
        # urlsplit validates bracketed hosts; accessing port validates its range.
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError(error)
    except ValueError:
        raise ValueError(error) from None
