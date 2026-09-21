"""Credential lifecycle; persist only Keychain references on macOS."""
from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import sys
from typing import Any

from . import extension_control as control, keychain


def single_key(values: dict[str, str]) -> str | None:
    unique = set(values.values())
    if len(unique) > 1:
        raise control.ControlError("key_ambiguous", "API key aliases disagree. Supply one unambiguous API key before migrating.")
    return keychain.validate_secret(next(iter(unique))) if unique else None


def legacy_snapshot(root: Path, config: dict[str, Any]) -> tuple[Path, bytes] | None:
    """Only the old installer's managed api.env is eligible for automatic cleanup."""
    path = root / "api.env"
    if config.get("credential_store") == "keychain" or config.get("env_file") != str(path):
        return None
    data = control._read(path, limit=65536)
    return (path, data) if data is not None else None


def cleanup_legacy(snapshot: tuple[Path, bytes]) -> None:
    """After verified migration, unlink the unchanged managed file; never back it up."""
    path, expected = snapshot
    try:
        if control._read(path, limit=65536) != expected:
            raise control.ControlError("keychain_cleanup", "Keychain migration succeeded, but api.env changed and was not removed. Review the old file manually.")
        parent = control._directory_fd(path.parent)
        try:
            os.unlink(path.name, dir_fd=parent)
            os.fsync(parent)
        finally:
            os.close(parent)
    except (OSError, control.ControlError):
        raise control.ControlError("keychain_cleanup", "The key is in Keychain, but the old api.env could not be safely removed. Review that file manually; no new plaintext backup was made.") from None


def manage(action: str, *, root: Path | None = None, secret: str | None = None) -> dict[str, Any]:
    if sys.platform != "darwin":
        raise control.ControlError("keychain_platform", "macOS Keychain is only available on macOS.")
    if action not in ("status", "set", "migrate", "delete"):
        raise control.ControlError("input", "Unknown credential action.")
    target = control._absolute(root) if root is not None else control.config_root()
    if action == "set":
        if secret is None:
            raise control.ControlError("key_format", "A non-empty key is required.")
        keychain.validate_secret(secret)
    with control._lock(target):
        config = control._load_config(target)
        secure = config.get("credential_store") == "keychain"
        account = keychain.account_id(target, Path(config["profile_dir"]))
        result = {"credential_store": "keychain" if secure else "env_file", "service": keychain.SERVICE,
                  "account": account, "key_status": "needs_migration"}
        if action == "status" or (action == "migrate" and secure):
            if secure:
                result["key_status"] = "configured" if keychain.get_store().contains(account) else "missing"
            return result
        if action == "delete":
            if not secure:
                raise control.ControlError("keychain_missing", "This installation still uses a legacy env file. No file was deleted.")
            result["deleted"] = keychain.get_store().delete(account)
            for name in control.KEY_NAMES:
                os.environ.pop(name, None)
            result["key_status"] = "missing"
            return result
        legacy = legacy_snapshot(target, config)
        if action == "migrate":
            # Migration means the referenced file, not an unrelated shell override.
            secret = single_key(control._key_values(config, include_environment=False))
            if secret is None:
                raise control.ControlError("key_missing", "The legacy key file contains no API key. Use keychain set instead.")
        updated = {**config, "credential_store": "keychain", "keychain_account": account, "env_file": None}
        control._transaction(target, [(target / "config.json", control._json_bytes(updated), 0o600)],
                             after_write=lambda: keychain.replace_verified(account, secret))
        if legacy is not None:
            cleanup_legacy(legacy)
        result.update(credential_store="keychain", key_status="configured", legacy_key_file_removed=legacy is not None)
        return result


def command(args: Any) -> int:
    if sys.platform != "darwin":
        raise control.ControlError("keychain_platform", "macOS Keychain is only available on macOS.")
    korean = getattr(args, "lang", "en") == "ko"
    secret = None
    if args.action == "set":
        if not sys.stdin.isatty():
            raise control.ControlError("terminal", "Use an interactive terminal for hidden key input, or setup --env-file to import a file.")
        prompt = "Jev API 키(입력 숨김): " if korean else "Jev API key (hidden): "
        secret = getpass.getpass(prompt).strip()
    if args.action == "delete" and not args.yes:
        if not sys.stdin.isatty():
            raise control.ControlError("confirmation", "Pass --yes to confirm deletion of this installation's Keychain item.")
        prompt = "이 설치의 키체인 항목을 삭제할까요? [y/N]: " if korean else "Delete this installation's Keychain item? [y/N]: "
        if input(prompt).strip().lower() not in ("y", "yes"):
            print("취소했습니다." if korean else "Cancelled.")
            return 0
    result = manage(args.action, root=Path(args.config_dir) if args.config_dir else None, secret=secret)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
