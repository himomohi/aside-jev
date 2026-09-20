"""명시적으로 선택한 Aside 프로필의 Jev 지침과 확장 설정을 관리한다."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys
from typing import Any, Callable, Iterator
import uuid

from .core import validate_confidence
from .jev import resolve_timeout
from .native_platform import ControlError
from . import native_platform, native_registry

HOST_NAME = "com.aside_jev.control"
BEGIN = "<!-- BEGIN aside-jev extension-control -->"
END = "<!-- END aside-jev extension-control -->"
LEGACY_BEGIN = "# BEGIN aside-jev"
LEGACY_END = "# END aside-jev"
SKILL_MARKER = "<!-- Managed by aside-jev extension-control. -->"
KEY_NAMES = ("TYPESAFE_API_KEY", "TYPESAFEAI_API_KEY")
MAX_FILE_BYTES = 262144


def config_root() -> Path:
    return _absolute(os.environ.get("ASIDE_JEV_CONFIG_DIR") or Path.home() / ".config" / "aside-jev")


def _absolute(path: str | Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _check_path(path: Path) -> None:
    if os.name == "nt":
        native_platform.validate_windows_path(path)
    # resolve()로 심볼릭 링크를 조용히 따라가지 않는다.
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or native_platform.is_reparse(info):
            raise ControlError("unsafe_path", "심볼릭 링크가 포함된 경로는 변경할 수 없습니다. 실제 프로필 경로를 지정해 주세요.")
        if part != path and not stat.S_ISDIR(info.st_mode):
            raise ControlError("unsafe_path", "설정 경로의 상위 항목이 폴더가 아닙니다.")


def _directory_fd(path: Path, *, create: bool = False) -> int:
    """각 상위 폴더를 링크를 따라가지 않고 열어 경로 교체의 영향을 줄인다."""
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path.anchor, flags)
    try:
        for name in path.parts[1:]:
            try:
                child = os.open(name, flags, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(name, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(name, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except Exception:
        os.close(fd)
        raise


def _read(path: Path, *, limit: int = MAX_FILE_BYTES) -> bytes | None:
    _check_path(path)
    if os.name == "nt":
        return native_platform.windows_read(path, limit)
    try:
        parent_fd = _directory_fd(path.parent)
    except FileNotFoundError:
        return None
    except OSError:
        raise ControlError("file_access", "설정 파일에 접근할 수 없습니다. 경로와 권한을 확인해 주세요.") from None
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
    except FileNotFoundError:
        return None
    except OSError:
        raise ControlError("file_access", "설정 파일에 접근할 수 없습니다. 경로와 권한을 확인해 주세요.") from None
    finally:
        os.close(parent_fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ControlError("unsafe_path", "설정 파일은 연결되지 않은 일반 파일이어야 합니다.")
        if info.st_size > limit:
            raise ControlError("file_size", "설정 파일이 허용 크기를 초과했습니다.")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            result = stream.read(limit + 1)
        if len(result) > limit:
            raise ControlError("file_size", "설정 파일이 허용 크기를 초과했습니다.")
        return result
    finally:
        os.close(fd)


def _text(path: Path, *, limit: int = MAX_FILE_BYTES) -> str | None:
    data = _read(path, limit=limit)
    if data is None:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ControlError("encoding", "설정 파일은 UTF-8 형식이어야 합니다.") from None


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _make_directory(path: Path) -> None:
    _check_path(path)
    if os.name == "nt":
        with native_platform.windows_directory(path, create=True):
            return
    fd = _directory_fd(path, create=True)
    os.close(fd)


def _atomic_write(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    _check_path(path)
    if os.name == "nt":
        native_platform.windows_atomic_write(path, data)
        return
    _make_directory(path.parent)
    if path.exists():
        _read(path)
    parent_fd = _directory_fd(path.parent)
    temporary = ".aside-jev-" + uuid.uuid4().hex
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), mode, dir_fd=parent_fd)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _check_path(path)
        try:
            destination = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            destination = None
        if destination is not None and (not stat.S_ISREG(destination.st_mode) or destination.st_nlink != 1):
            raise ControlError("unsafe_path", "설정 대상이 변경되어 저장을 중단했습니다.")
        os.replace(temporary, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        os.close(parent_fd)


@contextmanager
def _lock(root: Path, *, create: bool = False) -> Iterator[None]:
    if create:
        _make_directory(root)
    elif not root.is_dir():
        raise ControlError("not_configured", "확장 연결을 먼저 설치해 주세요. 설치 미리보기 명령에서 프로필과 확장 ID를 지정할 수 있습니다.")
    _check_path(root / ".lock")
    if os.name == "nt":
        with native_platform.windows_lock(root / ".lock"):
            yield
        return
    import fcntl
    parent_fd = _directory_fd(root)
    try:
        fd = os.open(".lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=parent_fd)
    finally:
        os.close(parent_fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ControlError("unsafe_path", "설정 잠금 파일을 안전하게 열 수 없습니다.")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ControlError("busy", "다른 설정 변경이 진행 중입니다. 잠시 후 다시 시도해 주세요.") from None
        yield
    finally:
        os.close(fd)


def _load_config(root: Path) -> dict[str, Any]:
    content = _text(root / "config.json", limit=65536)
    if content is None:
        raise ControlError("not_configured", "확장 연결이 설정되지 않았습니다. 설치 미리보기에서 대상 프로필을 지정해 주세요.")
    try:
        result = json.loads(content)
        if not isinstance(result, dict) or result.get("version") != 1:
            raise ValueError()
        if not re.fullmatch(r"[a-p]{32}", result["extension_id"]):
            raise ValueError()
        if not isinstance(result["enabled"], bool):
            raise ValueError()
        for name in ("profile_dir", "python_executable", "mcp_wrapper"):
            if not isinstance(result[name], str) or not Path(result[name]).is_absolute():
                raise ValueError()
        if result.get("env_file") is not None and (not isinstance(result["env_file"], str) or not Path(result["env_file"]).is_absolute()):
            raise ValueError()
        validate_confidence(result["min_confidence"], name="min_confidence")
        resolve_timeout(result["timeout_s"])
        if result["model"] != "jev-latest" or not isinstance(result.get("profile_label"), str):
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise ControlError("configuration", "확장 설정 파일이 올바르지 않습니다. 설치 명령으로 대상과 설정을 다시 확인해 주세요.") from None
    _check_path(Path(result["profile_dir"]))
    if not Path(result["profile_dir"]).is_dir():
        raise ControlError("profile_missing", "설정한 Aside 프로필 폴더를 찾을 수 없습니다.")
    return result


def validate_origin(origin: str) -> None:
    with _lock(config_root()):
        config = _load_config(config_root())
        if origin != f"chrome-extension://{config['extension_id']}/":
            raise ControlError("origin", "등록한 Aside Jev 확장 프로그램만 이 연결을 사용할 수 있습니다.")


def _key_values(config: dict[str, Any]) -> dict[str, str]:
    values = {name: value.strip() for name in KEY_NAMES if (value := os.environ.get(name, "")).strip()}
    if values:
        return values
    if not config.get("env_file"):
        return {}
    content = _text(Path(config["env_file"]), limit=65536)
    if content is None:
        raise ControlError("key_file", "지정한 API 키 환경 파일을 찾을 수 없습니다.")
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            words = shlex.split(stripped, comments=True, posix=True)
        except ValueError:
            raise ControlError("key_file", "API 키 파일에는 허용된 키의 단순 할당만 작성해 주세요.") from None
        if words and words[0] == "export":
            words = words[1:]
        if len(words) != 1 or "=" not in words[0]:
            raise ControlError("key_file", "API 키 파일에는 허용된 키의 단순 할당만 작성해 주세요.")
        name, value = words[0].split("=", 1)
        if name not in KEY_NAMES or any(character in value for character in ("$", "`", ";", "\n", "\r")):
            raise ControlError("key_file", "API 키 파일은 TYPESAFE_API_KEY 또는 TYPESAFEAI_API_KEY의 고정 값만 지원합니다.")
        if value.strip():
            values[name] = value.strip()
    return values


def load_key_environment() -> bool:
    """허용된 키만 읽으며 source, 변수 확장, 셸 실행을 하지 않는다."""
    root = config_root()
    with _lock(root):
        values = _key_values(_load_config(root))
        for name, value in values.items():
            os.environ[name] = value
        return bool(values)


def _rules(config: dict[str, Any]) -> str:
    return f"""{BEGIN}
## Aside Jev 확장: 브라우저 판단 경로
이 구간은 Aside Jev 확장이 관리한다. 새 Aside 작업에 적용되는 지침이며 네이티브 도구 호출을 기술적으로 가로채는 기능은 아니다.
- 브라우저 사용을 시작하기 전 aside-jev 스킬과 확장 상태를 확인한다. OFF 상태에서는 이 확장의 절차를 적용하지 않는다.
- 여러 페이지를 이동하는 연속 브라우저 작업은 MCP `jev_browser_run`을 우선 사용한다. 허용할 행동과 명시적인 완료 조건을 제공하고, 매 단계 관찰 → 간결한 상태 → live Jev 선택 → Aside 실행 → 새 관찰 흐름을 유지한다. 이전 페이지의 ref를 재사용하지 않는다.
- 모든 다음 브라우저 행동은 현재 관찰에서 실행 가능한 완전한 후보와 abstain을 만들고 MCP `jev_step`으로 판단한다. provider는 live, model은 {config['model']}, 최소 신뢰도는 {config['min_confidence']}, HTTP 단계별 한도는 {config['timeout_s']}초다.
- 실행 도구·선택자·인자를 Jev 응답 후 임의로 변경하지 않는다. Jev가 선택한 검증된 후보 한 개만 기존 Aside 권한과 사용자 승인 범위 안에서 실행하고 새 관찰로 결과를 확인한다.
- 완료 여부는 `jev_system_one`의 Noul, 위험도는 Score로 판단한다. 위험 평가용 rubric은 작업 맥락에 명시하고 민감한 작업의 사용자 승인을 생략하지 않는다.
- MCP 미연결, 키 없음, Jev 오류, 부정확한 응답, 낮은 신뢰도 또는 abstain이면 즉시 중단한다. mock이나 기존 모델의 독자적 선택으로 우회하지 않는다.
- MCP 서버는 `aside-jev serve --extension` 연결을 사용한다. 확장 ON은 서버가 Aside에 등록되었다는 뜻이 아니다. 미연결이면 설정 안내 후 중단한다.
- 브라우저·컴퓨터 전체 판단이 기술적으로 강제된다고 설명하지 않는다. 적용 범위는 새 Aside 작업의 지침이며 기존 작업에는 자동 소급되지 않는다.
{END}
"""


def _skill(config: dict[str, Any]) -> str:
    if config.get("platform") == "windows":
        command = '"' + str(Path(config["mcp_wrapper"]).parent / "status-host.cmd") + '"'
    else:
        command = "ASIDE_JEV_CONFIG_DIR=" + shlex.quote(str(Path(config["mcp_wrapper"]).parent)) + " " + shlex.join([config["python_executable"], "-m", "aside_jev.cli", "extension-status"])
    return f"""---
name: aside-jev
description: Aside 브라우저 행동 선택, 완료 여부, 위험 판단에 Jev를 사용하는 사용자 설치 확장. 사용 전에 확장 상태를 확인한다.
---
{SKILL_MARKER}
# Aside Jev
먼저 `{command}`로 확장 상태를 확인한다.
`enabled`와 `instructions_applied`가 true인지 확인한다. OFF이면 이 스킬의 판단 경로를 적용하지 않는다.
ON이면 각 브라우저 행동에 대해 앱이 소유한 후보 표를 만들고 live MCP `jev_step`으로 다음 한 개를 선택한다.
연속된 브라우저 작업은 MCP `jev_browser_run`을 우선 사용한다. 허용된 행동과 완료 조건을 지정하고 각 행동 후 새 관찰을 받아 ref를 갱신한다.
완료·위험 평가는 live MCP `jev_system_one`의 Noul/Score를 사용한다.
연결 실패·인증 실패·낮은 신뢰도·abstain이면 행동을 멈춘다. mock 또는 독자 판단으로 대체하지 않는다.
기존 Aside 권한과 민감한 행동의 사용자 승인 경계를 유지한다.
본 스킬과 AGENTS 지침은 모델에게 요구하는 절차다. 내장 브라우저 도구 전체의 네이티브 차단이나 전역 모델 교체를 보장하지 않는다.
"""


def _strip_blocks(text: str) -> tuple[str, int, int]:
    removed = 0
    legacy = 0
    for begin, end in ((BEGIN, END), (LEGACY_BEGIN, LEGACY_END)):
        begin_count = sum(line.strip() == begin for line in text.splitlines())
        end_count = sum(line.strip() == end for line in text.splitlines())
        pattern = re.compile(r"(?m)^" + re.escape(begin) + r"\r?\n(?:(?!^" + re.escape(begin) + r"\r?$).)*?^" + re.escape(end) + r"(?:\r?\n|$)", re.DOTALL)
        matches = list(pattern.finditer(text))
        if begin_count != end_count or len(matches) != begin_count:
            raise ControlError("managed_block", "Jev 관리 구간 표시가 손상되어 있습니다. 백업과 원본을 확인해 주세요.")
        text, count = pattern.subn("", text)
        removed += count
        if begin == LEGACY_BEGIN:
            legacy += count
    return text, removed, legacy


def _paths(root: Path, config: dict[str, Any]) -> tuple[Path, Path]:
    profile = Path(config["profile_dir"])
    return profile / "AGENTS.md", profile / "skills" / "user" / "aside-jev" / "SKILL.md"


def _legacy_rule_paths() -> dict[str, Path]:
    home = Path.home()
    return {"user_home": home / "AGENTS.md", "aside_global": home / ".aside" / "AGENTS.md"}


def _legacy_warnings(config: dict[str, Any]) -> tuple[list[str], list[str]]:
    present, warnings = [], []
    target = Path(config["profile_dir"]) / "AGENTS.md"
    for label, path in _legacy_rule_paths().items():
        if path == target:
            continue
        try:
            text = _text(path) or ""
        except (ControlError, OSError):
            warnings.append(f"전역 지침({label})의 옛 Jev 규칙 여부를 확인하지 못했습니다. 해당 파일은 변경하지 않았습니다.")
            continue
        if any(line.strip() == LEGACY_BEGIN for line in text.splitlines()):
            present.append(label)
    if present:
        warnings.append("전역 AGENTS.md에 옛 Jev 규칙이 남아 있습니다. OFF는 선택한 프로필의 관리 구간만 제거하므로 기존 전역 지침의 영향이 남을 수 있습니다. 전역 파일은 변경하지 않았습니다.")
    return present, warnings


def _status(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    agents_path, skill_path = _paths(root, config)
    agents = _text(agents_path) or ""
    skill = _text(skill_path) or ""
    _, block_count, legacy_count = _strip_blocks(agents)
    applied = agents.count(_rules(config)) == 1 and block_count == 1 and legacy_count == 0 and skill == _skill(config)
    try:
        ready = bool(_key_values(config))
        key_status = "configured" if ready else "missing"
    except ControlError:
        ready, key_status = False, "file_error"
    legacy_global, warnings = _legacy_warnings(config)
    entry = _mcp_entry(config)
    try:
        settings = json.loads(_text(Path(config["profile_dir"]) / "settings.json") or "{}")
        mcp_registered = settings.get("mcp", {}).get("servers", {}).get("aside-jev") == entry
    except (ControlError, ValueError, AttributeError, OSError):
        mcp_registered = False
    return {
        "configured": True,
        "enabled": bool(config["enabled"] and applied),
        "desired_enabled": config["enabled"],
        "instructions_applied": applied,
        "live_available": ready,
        "key_status": key_status,
        "model": config["model"],
        "min_confidence": config["min_confidence"],
        "timeout_s": config["timeout_s"],
        "profile_label": config["profile_label"],
        "enforcement": "instructions_only",
        "scope": "new_aside_tasks",
        "native_interception": False,
        "mcp_registration": "configured" if mcp_registered else "manual",
        "mcp_connected": None,
        "legacy_blocks": legacy_count,
        "legacy_global_rules": legacy_global,
        "warnings": warnings,
        "mcp_config": {"mcpServers": {"aside-jev": {"command": entry["command"], "args": entry["args"]}}},
        "aside_mcp_entry": entry,
    }


def _mcp_entry(config: dict[str, Any]) -> dict[str, Any]:
    if config.get("platform") == "windows":
        command = config["python_executable"]
        args = ["-I", str(Path(config["mcp_wrapper"]).parent / "mcp-entry.py")]
    else:
        command, args = config["mcp_wrapper"], []
    return {"enabled": True, "transport": "stdio", "command": command, "args": args, "env": {}}


def get_status() -> dict[str, Any]:
    root = config_root()
    with _lock(root):
        return _status(root, _load_config(root))


def load_runtime_policy() -> dict[str, Any]:
    status = get_status()
    return {name: status[name] for name in ("enabled", "model", "min_confidence", "timeout_s")}


def _transaction(root: Path, updates: list[tuple[Path, bytes, int]], *, after_write: Callable[[], None] | None = None) -> None:
    changed: list[tuple[Path, bytes, int, bytes | None, int]] = []
    for path, data, mode in updates:
        original = _read(path)
        previous_mode = stat.S_IMODE(path.stat().st_mode) if original is not None else mode
        if original != data:
            changed.append((path, data, mode, original, previous_mode))
    if not changed:
        if after_write is not None:
            after_write()
        return
    backup_root = root / "backups"
    _make_directory(backup_root)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    record = []
    for index, (path, _, _, original, _) in enumerate(changed):
        backup = backup_root / f"{stamp}-{index}.bak"
        if original is not None:
            _atomic_write(backup, original)
        record.append({"path": str(path), "existed": original is not None, "backup": str(backup) if original is not None else None})
    _atomic_write(backup_root / f"{stamp}.json", _json_bytes({"files": record}))
    completed: list[tuple[Path, bytes, bytes | None, int]] = []
    try:
        for path, data, mode, original, previous_mode in changed:
            if _read(path) != original:
                raise ControlError("file_changed", "다른 작업이 설정 파일을 변경해 저장을 중단했습니다.")
            # rename 직후 fsync가 실패해도 이번 대상까지 원복 목록에 포함한다.
            completed.append((path, data, original, previous_mode))
            _atomic_write(path, data, mode=mode)
        if after_write is not None:
            after_write()
    except Exception as error:
        try:
            for path, data, original, previous_mode in reversed(completed):
                current = _read(path)
                if current == original:
                    continue
                if current != data:
                    raise ControlError("file_changed", "다른 작업의 변경이 있어 자동 원복을 중단했습니다.")
                if original is None:
                    _check_path(path)
                    if os.name == "nt":
                        native_platform.windows_unlink(path)
                    else:
                        parent_fd = _directory_fd(path.parent)
                        try:
                            os.unlink(path.name, dir_fd=parent_fd)
                        finally:
                            os.close(parent_fd)
                else:
                    _atomic_write(path, original, mode=previous_mode)
        except Exception:
            raise ControlError("rollback_failed", "변경을 전부 되돌리지 못했습니다. 확장을 사용하지 말고 설정 폴더의 backups 기록을 확인해 주세요.") from None
        if isinstance(error, ControlError) and error.code in ("registry_write", "registry_access", "rollback_failed"):
            raise error
        raise ControlError("write_failed", "설정을 저장하지 못해 변경을 되돌렸습니다. 파일 권한을 확인해 주세요.") from None


def _apply(root: Path, config: dict[str, Any], enabled: bool) -> dict[str, Any]:
    if enabled and not _key_values(config):
        raise ControlError("key_missing", "Jev API 키가 필요합니다. 설치 시 지정한 환경 파일 또는 서버 환경변수에 설정해 주세요.")
    agents_path, skill_path = _paths(root, config)
    original = _text(agents_path) or ""
    base, removed, _ = _strip_blocks(original)
    # 확장이 추가한 줄바꿈만 되돌리며 사용자 본문은 그대로 남긴다.
    if removed and config.get("added_separator") and base.endswith("\n"):
        base = base[:-1]
    updates: list[tuple[Path, bytes, int]] = []
    if enabled:
        existing_skill = _text(skill_path)
        if existing_skill and SKILL_MARKER not in existing_skill and "# aside-jev (Aside browse → Jev)" not in existing_skill:
            raise ControlError("skill_conflict", "선택한 프로필에 다른 aside-jev 스킬이 있습니다. 기존 파일을 확인한 뒤 설치해 주세요.")
        separator = bool(base and not base.endswith("\n"))
        result = base + ("\n" if separator else "") + _rules(config)
        config = {**config, "enabled": True, "added_separator": separator}
        updates.append((skill_path, _skill(config).encode(), 0o600))
    else:
        result = base
        config = {**config, "enabled": False, "added_separator": False}
    if original != result:
        mode = stat.S_IMODE(agents_path.stat().st_mode) if agents_path.exists() else 0o600
        updates.append((agents_path, result.encode(), mode))
    updates.append((root / "config.json", _json_bytes(config), 0o600))
    _transaction(root, updates)
    return _status(root, config)


def set_enabled(enabled: bool) -> dict[str, Any]:
    if not isinstance(enabled, bool):
        raise ControlError("input", "enabled는 true 또는 false여야 합니다.")
    root = config_root()
    with _lock(root):
        return _apply(root, _load_config(root), enabled)


def configure(*, min_confidence: float | None = None, timeout_s: float | None = None) -> dict[str, Any]:
    root = config_root()
    with _lock(root):
        config = _load_config(root)
        try:
            if min_confidence is not None:
                config["min_confidence"] = validate_confidence(min_confidence, name="min_confidence")
            if timeout_s is not None:
                config["timeout_s"] = resolve_timeout(timeout_s)
        except ValueError:
            raise ControlError("input", "최소 신뢰도는 0~1, HTTP 단계별 한도는 1~60초여야 합니다.") from None
        return _apply(root, config, config["enabled"])


def setup_installation(
    *, extension_id: str, profile_dir: str | Path, native_host_dir: str | Path,
    env_file: str | Path | None = None, profile_label: str | None = None,
    apply: bool = False, root: str | Path | None = None,
    windows_registry_key: str | None = None,
    extra_updates: list[tuple[Path, bytes, int]] | None = None,
    expected_files: dict[Path, bytes | None] | None = None,
) -> dict[str, Any]:
    """미리보기가 기본이며 apply=True를 명시한 설치에서만 연결 파일을 만든다."""
    if not re.fullmatch(r"[a-p]{32}", extension_id):
        raise ControlError("input", "확장 ID는 a~p 소문자 32자리여야 합니다.")
    target_root = _absolute(root) if root is not None else config_root()
    profile, hosts = _absolute(profile_dir), _absolute(native_host_dir)
    environment_file = _absolute(env_file) if env_file is not None else None
    for path in (target_root, profile, hosts):
        _check_path(path)
    if not profile.is_dir():
        raise ControlError("profile_missing", "기존 Aside 계정 프로필 폴더를 명시해 주세요.")
    if environment_file is not None:
        _check_path(environment_file)
    python = os.path.abspath(sys.executable)
    platform = native_platform.platform_name()
    windows = platform == "windows"
    if windows:
        native_platform.validate_windows_launcher_path(target_root)
        windows_registry_key = native_registry.validate_registry_key(windows_registry_key, HOST_NAME)
    elif windows_registry_key is not None:
        raise ControlError("registry_target", "Windows 레지스트리 등록은 Windows에서만 지원합니다.")
    native_wrapper = target_root / ("native-host.cmd" if windows else "native-host")
    mcp_wrapper = target_root / ("mcp-host.cmd" if windows else "mcp-host")
    manifest_path = hosts / f"{HOST_NAME}.json"
    config = {
        "version": 1, "extension_id": extension_id, "profile_dir": str(profile),
        "profile_label": (profile_label or profile.name)[:120], "env_file": str(environment_file) if environment_file else None,
        "python_executable": python, "mcp_wrapper": str(mcp_wrapper),
        "enabled": False, "model": "jev-latest", "min_confidence": 0.7, "timeout_s": 15.0,
        "added_separator": False,
        "platform": platform, "windows_registry_key": windows_registry_key,
    }
    manifest = {"name": HOST_NAME, "description": "Aside Jev profile instruction control", "path": str(native_wrapper), "type": "stdio", "allowed_origins": [f"chrome-extension://{extension_id}/"]}
    registered = _text(manifest_path, limit=65536)
    if registered is not None:
        try:
            prior_manifest = json.loads(registered)
            if prior_manifest.get("path") != str(native_wrapper) or prior_manifest.get("allowed_origins") != manifest["allowed_origins"]:
                raise ValueError()
        except (ValueError, AttributeError):
            raise ControlError("installation_conflict", "같은 이름의 Native Messaging 연결이 다른 대상에 등록되어 있습니다. 기존 연결을 먼저 확인해 주세요.") from None
    if windows:
        scripts = [
            (native_wrapper, native_platform.windows_launcher(python, native=True), 0o700),
            (mcp_wrapper, native_platform.windows_launcher(python, native=False), 0o700),
            (target_root / "native-entry.py", native_platform.windows_entry(native=True), 0o600),
            (target_root / "mcp-entry.py", native_platform.windows_entry(native=False), 0o600),
            (target_root / "status-host.cmd", native_platform.windows_status_launcher(python), 0o700),
            (target_root / "status-entry.py", native_platform.windows_status_entry(), 0o600),
        ]
    else:
        prefix = f"#!/bin/sh\n# 설치한 고정 경로만 실행한다. 입력을 셸 코드로 평가하지 않는다.\nexport ASIDE_JEV_CONFIG_DIR={shlex.quote(str(target_root))}\n"
        scripts = [
            (native_wrapper, (prefix + f"exec {shlex.quote(python)} -m aside_jev.cli native-host \"$@\"\n").encode(), 0o700),
            (mcp_wrapper, (prefix + f"exec {shlex.quote(python)} -m aside_jev.cli serve --extension\n").encode(), 0o700),
        ]
    registration = native_registry.prepare_registration(windows_registry_key, str(manifest_path), str(target_root)) if windows else None
    extras = [(_absolute(path), data, mode) for path, data, mode in (extra_updates or [])]
    expectations = {_absolute(path): expected for path, expected in (expected_files or {}).items()}
    generated_paths = [target_root / "config.json", *(path for path, _, _ in scripts), manifest_path]
    all_paths = [*generated_paths, *(path for path, _, _ in extras)]
    if len(set(all_paths)) != len(all_paths):
        raise ControlError("input", "설치 파일 목록에 중복된 대상 경로가 있습니다.")
    for path, data, mode in extras:
        _check_path(path)
        if not isinstance(data, bytes) or len(data) > MAX_FILE_BYTES or mode not in (0o600, 0o644, 0o700, 0o755):
            raise ControlError("input", "추가 설치 파일의 내용·크기·권한이 올바르지 않습니다.")
    for path, expected in expectations.items():
        _check_path(path)
        if expected is not None and not isinstance(expected, bytes):
            raise ControlError("input", "설치 전 파일 상태는 바이트 또는 빈 상태로 지정해 주세요.")
    plan = {
        "apply": apply, "extension_id": extension_id, "profile_label": config["profile_label"],
        "files": [str(path) for path in all_paths],
        "aside_mcp_entry": _mcp_entry(config),
        "native_host": manifest, "enforcement": "instructions_only", "scope": "new_aside_tasks",
        "platform": platform,
        "registry_registration": {"hive": "HKCU", "key": windows_registry_key, "view": "32", "manifest": str(manifest_path)} if windows else None,
        "starts_background_service": False, "mcp_registration": "manual",
        "disable": "확장 팝업에서 OFF로 전환하면 선택한 프로필의 관리 지침만 제거됩니다. 등록 파일은 설치 미리보기의 files 목록에서 확인할 수 있습니다.",
    }
    if not apply:
        return plan
    with _lock(target_root, create=True):
        for path, expected in expectations.items():
            if _read(path) != expected:
                raise ControlError("file_changed", "설치 미리보기 이후 파일이 변경되어 중단했습니다. 새 미리보기를 확인해 주세요.")
        existing = _text(target_root / "config.json", limit=65536)
        if existing is not None:
            previous = _load_config(target_root)
            identity = ("extension_id", "profile_dir", "env_file", "windows_registry_key")
            if any(previous.get(name) != config[name] for name in identity):
                raise ControlError("installation_conflict", "기존 연결이 다른 대상에 설치되어 있습니다. 기존 연결을 해제한 뒤 별도 설정 폴더를 사용해 주세요.")
            config = {**config, **{name: previous[name] for name in ("enabled", "min_confidence", "timeout_s", "added_separator")}}
        elif any(_read(path) is not None for path, _, _ in scripts):
            raise ControlError("installation_conflict", "설치 폴더에 소유권을 확인할 수 없는 실행 파일이 있습니다. 별도 설정 폴더를 사용해 주세요.")
        _transaction(target_root, [
            (target_root / "config.json", _json_bytes(config), 0o600),
            *scripts,
            (manifest_path, _json_bytes(manifest), 0o600),
            *extras,
        ], after_write=registration.apply if registration is not None else None)
    return plan
