#!/usr/bin/env python3
"""임시 계정에서 설치·설정 보존·Native Messaging 왕복을 검증한다."""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
from typing import Any
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
HOST = "com.aside_jev.control"
EXTENSION_ID = "pendehmejnpgceflngbnbpagpodiiemg"
KEY_NAMES = ("TYPESAFE_API_KEY", "TYPESAFEAI_API_KEY")


class VerificationError(RuntimeError):
    def __init__(self, code: str, *, returncode: int | None = None, output_tail: str | None = None):
        super().__init__(code)
        self.code, self.returncode, self.output_tail = code, returncode, output_tail


def require(condition: bool, code: str) -> None:
    if not condition:
        raise VerificationError(code)


def sanitized_tail(raw: bytes | str | None, environment: dict[str, str]) -> str:
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else (raw or "")
    # 전체 출력에서 먼저 비밀 패턴을 제거하고 마지막 다섯 줄만 남긴다.
    for name, value in environment.items():
        if len(value) >= 4 and re.search(r"(?i)key|token|password|secret|auth|credential", name):
            text = text.replace(value, "[REDACTED]")
    text = re.sub(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@", r"\1[REDACTED]@", text)
    text = re.sub(r"(?im)(authorization\s*[:=]\s*)[^\r\n]+", r"\1[REDACTED]", text)
    text = re.sub(r'''(?i)(["']?[\w-]*(?:api[_-]?key|token|password|secret|credential)[\w-]*["']?\s*[:=]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;}\]]+)''', r"\1[REDACTED]", text)
    text = re.sub(r"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\b", "[REDACTED]", text)
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = "".join(character for character in text if character in "\n\t" or ord(character) >= 32)
    return "\n".join(text.splitlines()[-5:])[-2000:]


def run(command: list[str], *, environment: dict[str, str], cwd: Path,
        timeout: int = 60, payload: bytes | None = None) -> subprocess.CompletedProcess:
    # 실패한 설치기의 예외·환경·본문을 CI 출력에 그대로 복제하지 않는다.
    arguments: dict[str, Any] = {"input": payload} if payload is not None else {"stdin": subprocess.DEVNULL}
    try:
        result = subprocess.run(command, cwd=cwd, env=environment, capture_output=True,
                                timeout=timeout, check=False, **arguments)
    except subprocess.TimeoutExpired as error:
        raise VerificationError("subprocess_timeout", output_tail=sanitized_tail(error.stderr or error.stdout, environment)) from None
    except OSError as error:
        raise VerificationError("subprocess_start_failed", output_tail=sanitized_tail(str(error), environment)) from None
    if result.returncode:
        raise VerificationError("subprocess_failed", returncode=result.returncode,
                                output_tail=sanitized_tail(result.stderr or result.stdout, environment))
    return result


def assets_from_tree(folder: Path) -> dict[str, bytes]:
    return {str(path.relative_to(folder)).replace(os.sep, "/"): path.read_bytes()
            for path in folder.rglob("*") if path.is_file()
            and not any(part.startswith(".") or part == "node_modules" for part in path.relative_to(folder).parts)}


def verify_identity(assets: dict[str, bytes]) -> None:
    manifest = json.loads(assets["manifest.json"])
    public_key = base64.b64decode(manifest["key"], validate=True)
    identity = "".join(chr(97 + int(character, 16)) for character in hashlib.sha256(public_key).hexdigest()[:32])
    require(identity == EXTENSION_ID, "extension_identity_changed")
    require(manifest["default_locale"] == "en", "extension_default_locale")
    require(all(name in assets for name in ("_locales/en/messages.json", "_locales/ko/messages.json", "popup.html", "popup.js")), "extension_assets_missing")


def verify_wheel(directory: Path, expected: dict[str, bytes]) -> int:
    candidates = sorted(directory.glob("aside_jev-*.whl"))
    require(len(candidates) == 1, "wheel_count")
    with zipfile.ZipFile(candidates[0]) as wheel:
        prefix = "aside_jev/extension_assets/"
        names = [name for name in wheel.namelist() if name.startswith(prefix) and not name.endswith("/")]
        require(len(names) == len(set(names)), "duplicate_wheel_assets")
        actual = {name[len(prefix):]: wheel.read(name) for name in names}
        require(actual == expected, "wheel_assets_differ")
        require(all(name in wheel.namelist() for name in ("aside_jev/installer.py", "aside_jev/native_platform.py", "aside_jev/native_registry.py")), "wheel_runtime_missing")
    return len(actual)


def registry_exists(key: str) -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
            return True
    except FileNotFoundError:
        return False


def cleanup_registry(key: str, *, owner: Path, manifest: Path, parent_existed: bool) -> None:
    import winreg
    # UUID 전용 키의 소유권이 달라졌으면 다른 값을 삭제하지 않고 실패를 보고한다.
    if registry_exists(key):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ | winreg.KEY_WOW64_32KEY) as handle:
            subkeys, count, _ = winreg.QueryInfoKey(handle)
            values = {name: (value, kind) for name, value, kind in (winreg.EnumValue(handle, i) for i in range(count))}
            require(subkeys == 0 and values == {"": (str(manifest), winreg.REG_SZ), "AsideJevOwner": (str(owner), winreg.REG_SZ)}, "registry_cleanup_ownership")
        winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER, key, winreg.KEY_WOW64_32KEY, 0)
    parents = [key.rsplit("\\", 1)[0], key.rsplit("\\", 2)[0]]
    if not parent_existed:
        parents.append(r"Software\AsideJevTest")
    for parent in parents:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, parent, 0, winreg.KEY_READ | winreg.KEY_WOW64_32KEY) as handle:
                subkeys, values, _ = winreg.QueryInfoKey(handle)
            if subkeys == 0 and values == 0:
                winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER, parent, winreg.KEY_WOW64_32KEY, 0)
        except FileNotFoundError:
            pass
    require(not registry_exists(key), "registry_cleanup_failed")


def read_native_response(data: bytes) -> dict[str, Any]:
    require(len(data) >= 4, "native_header_missing")
    length = struct.unpack("=I", data[:4])[0]
    require(0 < length <= 128 * 1024 and len(data) == length + 4, "native_frame_invalid")
    response = json.loads(data[4:].decode("utf-8"))
    require(isinstance(response, dict), "native_response_invalid")
    return response


def verify(args: argparse.Namespace, report: dict[str, Any]) -> None:
    require(sys.platform in ("darwin", "win32"), "unsupported_platform")
    windows = sys.platform == "win32"
    if windows:
        require(args.allow_test_registry and os.environ.get("GITHUB_ACTIONS") == "true"
                and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted", "ephemeral_ci_registry_required")
    expected_assets = assets_from_tree(ROOT / "extension")
    verify_identity(expected_assets)
    if args.wheel_dir:
        report["stage"] = "wheel_assets"
        report["checks"]["wheel_assets"] = verify_wheel(args.wheel_dir, expected_assets)
    with tempfile.TemporaryDirectory(prefix="aside-jev-install-test-") as temporary:
        # macOS /var 별칭을 실제 임시 디렉터리 경로로 바꾼다.
        base = Path(temporary).resolve()
        profile = base / "synthetic 계정 with spaces"
        profile.mkdir()
        root, hosts, runtime = base / "config 공간", base / "hosts 공간", base / "runtime 공간"
        settings = {"theme": "keep-me", "custom": {"nested": [1, "보존"]},
                    "mcp": {"servers": {"existing-server": {"command": "example-only"}}, "inventories": {"keep": True}}}
        settings_path = profile / "settings.json"
        settings_path.write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")
        environment = dict(os.environ)
        for name in (*KEY_NAMES, "ASIDE_JEV_EXTENSION_MODE", "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
            environment.pop(name, None)
        environment.update(ASIDE_JEV_CONFIG_DIR=str(root), ASIDE_JEV_INSTALL_DIR=str(runtime),
                           PYTHONUTF8="1")
        registry_key = "\\".join(("Software", "AsideJevTest", uuid.uuid4().hex, "NativeMessagingHosts", HOST)) if windows else None
        parent_existed = registry_exists(r"Software\AsideJevTest") if windows else False
        if windows:
            require(not registry_exists(registry_key), "registry_test_collision")
        manifest_path = hosts / f"{HOST}.json"
        setup_args = ["--yes", "--profile-dir", str(profile), "--config-dir", str(root), "--native-host-dir", str(hosts)]
        if registry_key:
            setup_args += ["--windows-registry-key", registry_key]
        try:
            report["stage"] = "bootstrap" if args.bootstrap else "setup"
            if args.bootstrap:
                command = [str(ROOT / "Install.cmd"), *setup_args] if windows else ["bash", str(ROOT / "scripts/install.sh"), *setup_args]
                run(command, environment=environment, cwd=base, timeout=420)
                python = runtime / "runtime" / ("Scripts/python.exe" if windows else "bin/python")
                require(python.is_file(), "bootstrap_python_missing")
            else:
                python = Path(sys.executable)
                run([str(python), "-I", "-X", "utf8", "-m", "aside_jev.cli", "setup", *setup_args], environment=environment, cwd=base)
            report["checks"]["bootstrap"] = args.bootstrap
            version = run([str(python), "-I", "-c", "import json,sys; print(json.dumps(list(sys.version_info[:3])))"],
                          environment=environment, cwd=base)
            installed_version = json.loads(version.stdout)
            if args.bootstrap:
                require(installed_version[:2] == [3, 11], "bootstrap_python_version")
            report["checks"]["installed_python"] = ".".join(map(str, installed_version))
            config = json.loads((root / "config.json").read_text(encoding="utf-8"))
            installed = json.loads(settings_path.read_text(encoding="utf-8"))
            preserved = copy.deepcopy(installed)
            entry = preserved["mcp"]["servers"].pop("aside-jev")
            require(preserved == settings, "settings_not_preserved")
            require(entry["enabled"] and entry["transport"] == "stdio", "mcp_entry_invalid")
            require(config["extension_id"] == EXTENSION_ID and config["enabled"] is False, "installation_config_invalid")
            require(assets_from_tree(root / "extension") == expected_assets, "installed_assets_differ")
            require(not (profile / "AGENTS.md").exists(), "off_install_changed_rules")
            report["checks"].update(settings_preserved=True, extension_assets=len(expected_assets), stable_extension_id=EXTENSION_ID, default_off=True)
            report["stage"] = "idempotent_setup"
            original_settings = settings_path.read_bytes()
            localized_setup = run([str(python), "-I", "-X", "utf8", "-m", "aside_jev.cli", "setup", "--lang", "ko", *setup_args], environment=environment, cwd=base)
            require("연결 파일을 설치했습니다" in localized_setup.stdout.decode("utf-8"), "korean_setup_output_missing")
            require(settings_path.read_bytes() == original_settings, "repeat_changed_settings")
            report["checks"].update(idempotent_setup=True, korean_setup_output=True)
            report["stage"] = "native_status"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            require(manifest["allowed_origins"] == [f"chrome-extension://{EXTENSION_ID}/"], "native_origin_scope")
            payload = b'{"op":"status"}'
            frame = struct.pack("=I", len(payload)) + payload
            command = [manifest["path"], f"chrome-extension://{EXTENSION_ID}/"]
            if windows:
                command.append("--parent-window=0")
            native = run(command, environment=environment, cwd=base, payload=frame, timeout=30)
            response = read_native_response(native.stdout)
            require(response.get("ok") is True, "native_status_error")
            status = response["status"]
            require(status["enabled"] is False and status["live_available"] is False
                    and status["enforcement"] == "instructions_only" and status["native_interception"] is False, "native_status_contract")
            require(not native.stderr, "native_stderr_output")
            report["checks"]["native_status_framed_roundtrip"] = True
            if windows:
                require(registry_exists(registry_key), "registry_registration_missing")
                report["checks"]["isolated_hkcu_registration"] = True
        finally:
            if windows:
                report["registry_cleanup"] = False
                cleanup_registry(registry_key, owner=root, manifest=manifest_path, parent_existed=parent_existed)
                report["registry_cleanup"] = True
    report["checks"]["temporary_files_removed"] = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap", action="store_true", help="실제 플랫폼 설치기를 임시 폴더에서 실행")
    parser.add_argument("--wheel-dir", type=Path, help="extension_assets를 검사할 wheel 폴더")
    parser.add_argument("--allow-test-registry", action="store_true", help="GitHub-hosted Windows 러너의 UUID 전용 HKCU 테스트 키 허용")
    args = parser.parse_args()
    report: dict[str, Any] = {"ok": False, "platform": sys.platform, "python": ".".join(map(str, sys.version_info[:3])),
                              "stage": "preflight", "checks": {}, "registry_cleanup": None,
                              "boundaries": {"real_user_profile_used": False, "aside_browser_connection_tested": False,
                                             "live_jev_called": False}}
    try:
        verify(args, report)
        report.update(ok=True, stage="complete")
    except VerificationError as error:
        report["error"] = {"code": error.code, "exit_code": error.returncode}
        if error.output_tail:
            report["error"]["output_tail"] = error.output_tail
    except Exception:
        # 로컬 경로·계정 설정·원문 예외에 포함될 수 있는 값을 출력하지 않는다.
        report["error"] = {"code": "verification_internal", "exit_code": None}
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
