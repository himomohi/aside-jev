"""설치자가 명시한 HKCU Native Messaging 항목만 소유권을 확인해 등록한다."""
from __future__ import annotations

from typing import Any

from .native_platform import ControlError

OWNER_VALUE = "AsideJevOwner"


def validate_registry_key(key: str | None, host_name: str) -> str:
    if not isinstance(key, str) or not key or any(c in key for c in "/\x00\r\n"):
        raise ControlError("registry_target", "확인한 Windows HKCU Native Messaging 상대 키를 명시해 주세요.")
    parts = key.split("\\")
    if (len(parts) < 4 or parts[0].lower() != "software" or
            parts[-2].lower() != "nativemessaginghosts" or parts[-1] != host_name or
            any(not part or part != part.strip() or part in (".", "..") for part in parts)):
        raise ControlError("registry_target", "HKCU의 Software\\…\\NativeMessagingHosts\\com.aside_jev.control 키만 지원합니다.")
    return key


class Registration:
    def __init__(self, key: str, manifest: str, owner: str, *, registry: Any = None):
        if registry is None:
            import winreg
            registry = winreg
        self.registry = registry
        self.key, self.manifest, self.owner = key, manifest, owner
        # 브라우저가 먼저 조회하는 32비트 뷰에만 명시적으로 등록한다.
        self.view = registry.KEY_WOW64_32KEY
        self.before = self.snapshot()
        self.other_view = self.snapshot(view=registry.KEY_WOW64_64KEY)
        for existing in (self.before, self.other_view):
            if existing is not None and (existing.get("") != (manifest, registry.REG_SZ) or
                                         existing.get(OWNER_VALUE) != (owner, registry.REG_SZ)):
                raise ControlError("installation_conflict", "해당 Native Messaging 레지스트리 키는 다른 설치가 소유합니다. 기존 등록을 변경하지 않았습니다.")

    def snapshot(self, *, view: int | None = None) -> dict[str, tuple[Any, int]] | None:
        registry = self.registry
        try:
            handle = registry.OpenKey(registry.HKEY_CURRENT_USER, self.key, 0, registry.KEY_READ | (self.view if view is None else view))
        except FileNotFoundError:
            return None
        with handle:
            subkeys, values, _ = registry.QueryInfoKey(handle)
            if subkeys:
                raise ControlError("installation_conflict", "Native Messaging 등록 아래에 다른 키가 있어 변경하지 않았습니다.")
            return {name: (value, kind) for name, value, kind in (registry.EnumValue(handle, i) for i in range(values))}

    def _restore(self, written: list[dict[str, tuple[Any, int]]]) -> None:
        registry = self.registry
        current = self.snapshot()
        if current == self.before:
            return
        if current not in written:
            raise ControlError("rollback_failed", "다른 작업이 레지스트리를 변경해 자동 원복을 중단했습니다. 설치 기록을 확인해 주세요.")
        if self.before is None:
            registry.DeleteKeyEx(registry.HKEY_CURRENT_USER, self.key, self.view, 0)
            return
        with registry.OpenKey(registry.HKEY_CURRENT_USER, self.key, 0, registry.KEY_SET_VALUE | self.view) as handle:
            for name in current:
                if name not in self.before:
                    registry.DeleteValue(handle, name)
            for name, (value, kind) in self.before.items():
                registry.SetValueEx(handle, name, 0, kind, value)
            registry.FlushKey(handle)

    def apply(self) -> None:
        registry = self.registry
        if self.snapshot() != self.before or self.snapshot(view=registry.KEY_WOW64_64KEY) != self.other_view:
            raise ControlError("file_changed", "다른 작업이 Native Messaging 등록을 변경해 설치를 중단했습니다.")
        expected = dict(self.before or {})
        written = [dict(expected)]
        try:
            with registry.CreateKeyEx(registry.HKEY_CURRENT_USER, self.key, 0,
                                      registry.KEY_READ | registry.KEY_SET_VALUE | self.view) as handle:
                # 새 키를 만든 직후에도 외부 등록이 끼어들었는지 다시 확인한다.
                current = self.snapshot()
                if current != (self.before or {}):
                    raise ControlError("file_changed", "다른 작업이 Native Messaging 등록을 변경해 설치를 중단했습니다.")
                for name, value in ((OWNER_VALUE, self.owner), ("", self.manifest)):
                    expected[name] = (value, registry.REG_SZ)
                    written.append(dict(expected))
                    registry.SetValueEx(handle, name, 0, registry.REG_SZ, value)
                registry.FlushKey(handle)
        except Exception:
            try:
                self._restore(written)
            except Exception:
                raise ControlError("rollback_failed", "Native Messaging 등록을 되돌리지 못했습니다. 설치를 중단하고 레지스트리 대상과 백업을 확인해 주세요.") from None
            raise ControlError("registry_write", "Native Messaging 등록에 실패하여 레지스트리 변경을 되돌렸습니다.") from None


def prepare_registration(key: str, manifest: str, owner: str) -> Registration:
    try:
        return Registration(key, manifest, owner)
    except OSError:
        raise ControlError("registry_access", "현재 사용자 레지스트리에 접근할 수 없습니다. 대상 키와 권한을 확인해 주세요.") from None
