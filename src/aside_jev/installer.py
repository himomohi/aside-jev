"""운영체제별 연결을 한 번에 준비하는 명시적 대화형 설치기."""
from __future__ import annotations

import base64
import copy
import getpass
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from . import extension_control as control
from . import credentials, keychain

MESSAGES = {
    "en": {
        "title": "Aside Jev · Setup",
        "intro": "Choose your account, review the changes, then load the extension. Quit Aside before applying to keep account settings from being overwritten.",
        "profiles": "Aside accounts found on this computer:",
        "choose": "Account number [1]: ",
        "profile": "Aside account folder (accountRoot): ",
        "hosts": "Aside NativeMessagingHosts folder: ",
        "registry": "Verified HKCU registry key for Aside (Software\\...\\NativeMessagingHosts\\com.aside_jev.control): ",
        "registry_help": "The Windows host key depends on the browser build. Supply the verified key; this installer never registers other browsers as a fallback.",
        "key": "Jev API key (hidden; Enter to configure later): ",
        "key_help": "The key is stored in a local, unencrypted file accessible to your account. It is never sent to the popup or printed.",
        "keychain_help": "macOS stores the key in your Keychain, not api.env. Access failures stop setup; there is no plaintext fallback. Existing backups and externally supplied env files are not deleted.",
        "keychain_label": "Credential storage",
        "review": "Ready to connect",
        "account": "Account",
        "extension": "Extension folder",
        "mcp": "MCP settings (existing settings preserved)",
        "key_file": "Local key file",
        "confirm": "Install these connections? [y/N]: ",
        "cancel": "Cancelled. No connection settings were changed.",
        "success": "Connection files installed. Browser connection still needs the final check below.",
        "finish": "1. Reopen Aside → Extensions → Developer mode → Load unpacked.\n2. Select the extension folder above, pin Aside Jev, then turn ON.\n3. Start a new task. If needed, enable the Aside CLI in Developer settings.",
        "missing_key": "API key not configured yet. Run setup again before turning ON.",
        "invalid": "Enter a valid choice or an existing absolute folder path.",
        "noninteractive": "Interactive setup needs a terminal. For a preview, pass --dry-run and the required paths.",
        "unsupported": "This guided installer supports Windows and macOS.",
        "settings": "Aside settings.json must be an existing JSON object. Launch and sign in to Aside first.",
        "conflict": "An existing aside-jev MCP entry belongs to a different setup. Review it in Aside before changing it.",
        "assets_conflict": "The extension folder is not owned by this installer. Choose another config directory.",
        "dry": "Preview only. No files or registry entries were changed.",
        "write_error": "Setup is incomplete. Review the error code and backups before retrying.",
    },
    "ko": {
        "title": "Aside Jev · 설치",
        "intro": "계정을 선택하고 변경 내용을 확인한 뒤 확장을 로드하세요. 계정 설정이 덮어써지지 않도록 적용 전에 Aside를 종료하세요.",
        "profiles": "이 컴퓨터에서 찾은 Aside 계정:",
        "choose": "계정 번호 [1]: ",
        "profile": "Aside 계정 폴더(accountRoot): ",
        "hosts": "Aside NativeMessagingHosts 폴더: ",
        "registry": "확인된 Aside HKCU 레지스트리 키(Software\\...\\NativeMessagingHosts\\com.aside_jev.control): ",
        "registry_help": "Windows 등록 키는 브라우저 빌드에 따라 다릅니다. 확인된 키를 지정하세요. 다른 브라우저를 대신 등록하지 않습니다.",
        "key": "Jev API 키(입력 숨김, 나중에 설정하려면 Enter): ",
        "key_help": "키는 이 계정에서 접근할 수 있는 암호화되지 않은 로컬 파일에 저장됩니다. 팝업으로 보내거나 출력하지 않습니다.",
        "keychain_help": "macOS에서는 api.env 대신 키체인에 저장합니다. 접근 실패 시 평문 저장으로 우회하지 않습니다. 기존 백업과 외부에서 지정한 환경 파일은 삭제하지 않습니다.",
        "keychain_label": "키 저장소",
        "review": "연결 준비 완료",
        "account": "계정",
        "extension": "확장 폴더",
        "mcp": "MCP 설정(기존 설정 보존)",
        "key_file": "로컬 키 파일",
        "confirm": "이 연결을 설치할까요? [y/N]: ",
        "cancel": "취소했습니다. 연결 설정을 변경하지 않았습니다.",
        "success": "연결 파일을 설치했습니다. 아래 단계에서 실제 브라우저 연결을 확인하세요.",
        "finish": "1. Aside 다시 열기 → 확장 관리 → 개발자 모드 → 압축해제된 확장 로드.\n2. 위 확장 폴더를 선택하고 Aside Jev를 고정한 뒤 ON으로 켜세요.\n3. 새 작업을 시작하세요. 필요하면 개발자 설정에서 Aside CLI를 활성화하세요.",
        "missing_key": "아직 API 키가 없습니다. ON으로 켜기 전에 설치를 다시 실행해 키를 입력하세요.",
        "invalid": "올바른 번호 또는 실제 존재하는 폴더의 절대 경로를 입력하세요.",
        "noninteractive": "대화형 설치는 터미널이 필요합니다. 미리보기는 --dry-run과 필요한 경로를 지정하세요.",
        "unsupported": "이 간편 설치기는 Windows와 macOS를 지원합니다.",
        "settings": "Aside settings.json이 기존 JSON 객체여야 합니다. 먼저 Aside를 실행하고 로그인하세요.",
        "conflict": "기존 aside-jev MCP가 다른 설치에 연결되어 있습니다. Aside에서 기존 연결을 먼저 확인하세요.",
        "assets_conflict": "이 설치기가 만든 확장 폴더가 아닙니다. 다른 설정 경로를 지정하세요.",
        "dry": "미리보기입니다. 파일과 레지스트리를 변경하지 않았습니다.",
        "write_error": "설치가 완료되지 않았습니다. 다시 시도하기 전에 오류 코드와 backups를 확인하세요.",
    },
}


def extension_files() -> dict[str, bytes]:
    resource = files("aside_jev").joinpath("extension_assets")
    if not resource.is_dir():
        resource = Path(__file__).resolve().parents[2] / "extension"
    result: dict[str, bytes] = {}

    def walk(folder: Any, prefix: str = "") -> None:
        for item in folder.iterdir():
            if item.name.startswith(".") or item.name == "node_modules":
                continue
            name = prefix + item.name
            if item.is_dir():
                walk(item, name + "/")
            elif item.is_file():
                result[name] = item.read_bytes()

    walk(resource)
    return result


def extension_id(assets: dict[str, bytes]) -> str:
    public = base64.b64decode(json.loads(assets["manifest.json"])["key"], validate=True)
    return "".join(chr(97 + int(c, 16)) for c in hashlib.sha256(public).hexdigest()[:32])


def discover_profiles(home: Path | None = None) -> list[Path]:
    # 계정 인증 파일을 읽지 않고 실제 설정 파일이 있는 계정 폴더만 찾는다.
    root = (home or Path.home()) / ".aside" / "u"
    if not root.is_dir() or root.is_symlink():
        return []
    return sorted(p for p in root.iterdir() if re.fullmatch(r"(?:u)?\d+", p.name)
                  and p.is_dir() and not p.is_symlink() and (p / "settings.json").is_file())


def default_hosts(home: Path | None = None) -> Path | None:
    parent = (home or Path.home()) / "Library" / "Application Support" / "Aside"
    return parent / "NativeMessagingHosts" if parent.is_dir() else None


def existing_windows_registration() -> str | None:
    """이미 존재하는 Aside Native Messaging 부모만 읽기 전용 후보로 사용한다."""
    import winreg

    parent = r"Software\Aside\NativeMessagingHosts"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive, parent, 0, winreg.KEY_READ | view):
                    return parent + "\\" + control.HOST_NAME
            except OSError:
                continue
    return None


def merge_mcp(original: bytes | None, entry: dict[str, Any], *, locale: str, previous_entry: dict[str, Any] | None = None) -> bytes:
    try:
        document = json.loads(original) if original else None
        if not isinstance(document, dict):
            raise ValueError()
        result = copy.deepcopy(document)
        mcp = result.setdefault("mcp", {})
        if not isinstance(mcp, dict):
            raise ValueError()
        servers = mcp.setdefault("servers", {})
        if not isinstance(servers, dict):
            raise ValueError()
    except (ValueError, UnicodeDecodeError):
        raise control.ControlError("settings", MESSAGES[locale]["settings"]) from None
    existing = servers.get("aside-jev")
    if existing is not None and existing != entry and existing != previous_entry:
        raise control.ControlError("mcp_conflict", MESSAGES[locale]["conflict"])
    servers["aside-jev"] = entry
    return control._json_bytes(result)


def setup(args: Any) -> int:
    locale = args.lang
    t = MESSAGES[locale]
    if sys.platform not in ("darwin", "win32"):
        raise control.ControlError("platform", t["unsupported"])
    interactive = sys.stdin.isatty()
    if not interactive and not args.dry_run and not args.yes:
        raise control.ControlError("terminal", t["noninteractive"])
    print(t["title"] + "\n" + t["intro"])
    root = control._absolute(args.config_dir) if args.config_dir else control.config_root()
    control._check_path(root)
    previous = None
    previous_bytes = control._read(root / "config.json")
    if previous_bytes is not None:
        previous = control._load_config(root)
    profiles = discover_profiles()
    if args.profile_dir:
        profile = control._absolute(args.profile_dir)
    elif previous:
        profile = Path(previous["profile_dir"])
    elif profiles:
        print(t["profiles"])
        for index, path in enumerate(profiles, 1):
            print(f"  {index}. {path}")
        if len(profiles) > 1 and not interactive:
            raise control.ControlError("profile_required", t["invalid"])
        chosen = input(t["choose"]).strip() or "1" if interactive else "1"
        if not chosen.isdigit() or not 1 <= int(chosen) <= len(profiles):
            raise control.ControlError("input", t["invalid"])
        profile = profiles[int(chosen) - 1]
    elif interactive and not args.yes:
        value = input(t["profile"]).strip().strip('"')
        if not value or not Path(value).expanduser().is_absolute():
            raise control.ControlError("input", t["invalid"])
        profile = control._absolute(value)
    else:
        raise control.ControlError("profile_required", t["settings"])
    assets = extension_files()
    identity = extension_id(assets)
    registry = args.windows_registry_key
    if sys.platform == "win32":
        hosts = control._absolute(args.native_host_dir) if args.native_host_dir else root / "NativeMessagingHosts"
        if not registry and previous:
            registry = previous.get("windows_registry_key")
        if not registry:
            registry = existing_windows_registration()
        if not registry:
            print(t["registry_help"])
            if interactive and not args.yes:
                registry = input(t["registry"]).strip()
            if not registry:
                raise control.ControlError("registry_required", t["registry_help"])
    else:
        hosts = control._absolute(args.native_host_dir) if args.native_host_dir else default_hosts()
        if hosts is None and interactive and not args.yes:
            value = input(t["hosts"]).strip().strip('"')
            if value and Path(value).expanduser().is_absolute():
                hosts = control._absolute(value)
        if hosts is None:
            raise control.ControlError("host_required", t["invalid"])
    environment = str(control._absolute(args.env_file or (previous or {}).get("env_file") or root / "api.env"))
    if args.env_file and not Path(environment).is_file():
        raise control.ControlError("key_file", t["invalid"])
    secure = sys.platform == "darwin"
    source = Path(environment) if Path(environment).is_file() else None
    source_bytes = control._read(source, limit=65536) if source is not None else None
    previous_secure = (previous or {}).get("credential_store") == "keychain"
    if secure and previous_secure and not args.env_file:
        # Do not replace a saved key with a stale shell environment on reinstall.
        have_key = keychain.get_store().contains(previous["keychain_account"])
        secret = ""
        source = None
    else:
        values = control._key_values({"env_file": str(source) if source else None},
                                     include_environment=not (secure and source is not None))
        have_key = bool(values)
        secret = (credentials.single_key(values) or "") if secure else (
            next(iter(values.values()), "") if not Path(environment).exists() and not args.env_file else "")
    help_key = "keychain_help" if secure else "key_help"
    if secure or (secret and not args.dry_run):
        print(t[help_key])
    if not have_key and not args.dry_run and interactive and not args.yes and not args.env_file:
        if not secure:
            print(t[help_key])
        secret = getpass.getpass(t["key"]).strip()
    if secret and (not secret.isascii() or re.search(r"[\s'\"`$#;\\]", secret)):
        raise control.ControlError("key_format", "Invalid API key format.")
    kwargs = dict(extension_id=identity, profile_dir=profile, native_host_dir=hosts,
                  env_file=None if secure else environment, root=root, windows_registry_key=registry)
    if secure:
        kwargs.update(credential_store="keychain", keychain_secret=secret or None)
    plan = control.setup_installation(**kwargs)
    settings_path = profile / "settings.json"
    original = control._read(settings_path)
    entry = plan["aside_mcp_entry"]
    old_entry = None
    if previous:
        old_entry = control._mcp_entry(previous)
    updated = merge_mcp(original, entry, locale=locale, previous_entry=old_entry)
    extension = root / "extension"
    marker = extension / ".aside-jev-owned"
    if extension.exists() and control._read(marker) != b"aside-jev installer v1\n":
        raise control.ControlError("assets_conflict", t["assets_conflict"])
    updates = [(extension / name, value, 0o600) for name, value in assets.items()]
    updates += [(marker, b"aside-jev installer v1\n", 0o600), (settings_path, updated, 0o600)]
    if secret and not secure:
        updates.append((Path(environment), ("TYPESAFE_API_KEY=" + secret + "\n").encode(), 0o600))
    elif not secure and not Path(environment).exists():
        updates.append((Path(environment), b"# Add TYPESAFE_API_KEY here, or rerun setup.\n", 0o600))
    expected = {path: control._read(path) for path, _, _ in updates}
    expected[settings_path] = original
    expected[root / "config.json"] = previous_bytes
    if secure and source is not None:
        expected[source] = source_bytes
    kwargs.update(extra_updates=updates, expected_files=expected)
    print("\n" + t["review"])
    for label, value in [(t["account"], profile), (t["extension"], extension), (t["mcp"], settings_path), (t["keychain_label"] if secure else t["key_file"], "macOS Keychain" if secure else environment)]:
        print(f"  {label}: {value}")
    for path in plan["files"]:
        print(f"  + {path}")
    if registry:
        print(f"  HKCU\\{registry}")
    if args.dry_run:
        print(t["dry"])
        return 0
    if not args.yes and input(t["confirm"]).strip().lower() not in ("y", "yes"):
        print(t["cancel"])
        return 0
    # 확인을 기다리는 동안 변경된 계정 설정은 덮어쓰지 않는다.
    if control._read(settings_path) != original:
        raise control.ControlError("file_changed", t["write_error"])
    control.setup_installation(**kwargs, apply=True)
    print("\n" + t["success"] + "\n" + t["finish"])
    if not (secret or have_key):
        print(t["missing_key"])
    return 0
