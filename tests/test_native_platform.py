import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

from aside_jev import extension_control as control, native_host, native_platform, native_registry

KEY = r"Software\Verified Test Browser\NativeMessagingHosts\com.aside_jev.control"
EXTENSION_ID = "a" * 32
ORIGIN = f"chrome-extension://{EXTENSION_ID}/"


class RegistryHandle:
    def __init__(self, identity):
        self.identity = identity

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeRegistry:
    HKEY_CURRENT_USER = "HKCU"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    KEY_WOW64_32KEY = 32
    KEY_WOW64_64KEY = 64
    REG_SZ = 1

    def __init__(self):
        self.data = {}
        self.fail_value = None
        self.fail_after_value = None
        self.fail_flush = False
        self.writes = []

    def _identity(self, hive, key, access):
        assert hive == self.HKEY_CURRENT_USER
        return (access & 96, key)

    def OpenKey(self, hive, key, reserved, access):
        identity = self._identity(hive, key, access)
        if identity not in self.data:
            raise FileNotFoundError()
        return RegistryHandle(identity)

    def CreateKeyEx(self, hive, key, reserved, access):
        identity = self._identity(hive, key, access)
        self.data.setdefault(identity, {})
        return RegistryHandle(identity)

    def QueryInfoKey(self, handle):
        return 0, len(self.data[handle.identity]), 0

    def EnumValue(self, handle, index):
        name, (value, kind) = list(self.data[handle.identity].items())[index]
        return name, value, kind

    def SetValueEx(self, handle, name, reserved, kind, value):
        if self.fail_value == name:
            self.fail_value = None
            raise PermissionError("simulated registry failure")
        self.data[handle.identity][name] = (value, kind)
        self.writes.append((handle.identity, name))
        if self.fail_after_value == name:
            self.fail_after_value = None
            raise PermissionError("simulated failure after write")

    def DeleteValue(self, handle, name):
        del self.data[handle.identity][name]

    def DeleteKeyEx(self, hive, key, access, reserved):
        del self.data[self._identity(hive, key, access)]

    def FlushKey(self, handle):
        if self.fail_flush:
            self.fail_flush = False
            raise OSError("simulated flush failure")


def isolate_windows_registration(monkeypatch):
    """기존 공통 테스트도 실제 HKCU 대신 명시적인 테스트 등록 대상을 사용한다."""
    if os.name != "nt":
        return
    registry = FakeRegistry()
    original = control.setup_installation
    def setup(**kwargs):
        kwargs.setdefault("windows_registry_key", KEY)
        return original(**kwargs)
    monkeypatch.setattr(control, "setup_installation", setup)
    monkeypatch.setattr(native_registry, "prepare_registration", lambda key, manifest, owner:
                        native_registry.Registration(key, manifest, owner, registry=registry))


@pytest.fixture
def fake_windows(monkeypatch):
    registry = FakeRegistry()
    monkeypatch.setattr(native_platform, "platform_name", lambda: "windows")
    monkeypatch.setattr(native_registry, "prepare_registration", lambda key, manifest, owner:
                        native_registry.Registration(key, manifest, owner, registry=registry))
    monkeypatch.setattr(control, "_legacy_rule_paths", lambda: {})
    return registry


@pytest.mark.parametrize("key", [None, "", r"HKCU\Software\Browser\NativeMessagingHosts\com.aside_jev.control",
                                 r"Software\Browser\NativeMessagingHosts\other.host", r"Software\..\NativeMessagingHosts\com.aside_jev.control",
                                 r"Software\Browser\Run\com.aside_jev.control", "Software\\Browser\n\\NativeMessagingHosts\\com.aside_jev.control"])
def test_registry_target_must_be_explicit_scoped_relative_key(key):
    with pytest.raises(control.ControlError) as error:
        native_registry.validate_registry_key(key, control.HOST_NAME)
    assert error.value.code == "registry_target"


def test_registry_install_is_owned_hkcu_only_and_idempotent():
    registry = FakeRegistry()
    manifest, owner = r"C:\Jev\hosts\control.json", r"C:\Jev"
    native_registry.Registration(KEY, manifest, owner, registry=registry).apply()
    native_registry.Registration(KEY, manifest, owner, registry=registry).apply()
    assert registry.data == {(32, KEY): {"": (manifest, 1), "AsideJevOwner": (owner, 1)}}


@pytest.mark.parametrize("view", [32, 64])
def test_registry_foreign_registration_is_never_overwritten(view):
    registry = FakeRegistry()
    registry.data[(view, KEY)] = {"": (r"C:\Someone\manifest.json", 1)}
    with pytest.raises(control.ControlError) as error:
        native_registry.Registration(KEY, r"C:\Jev\manifest.json", r"C:\Jev", registry=registry)
    assert error.value.code == "installation_conflict"
    assert not registry.writes
    assert list(registry.data) == [(view, KEY)]


@pytest.mark.parametrize("failure", ["owner_before", "default_before", "owner_after", "default_after", "flush"])
def test_registry_partial_write_failure_restores_absent_key(failure):
    registry = FakeRegistry()
    if failure == "flush":
        registry.fail_flush = True
    else:
        name = "AsideJevOwner" if failure.startswith("owner") else ""
        setattr(registry, "fail_after_value" if failure.endswith("after") else "fail_value", name)
    registration = native_registry.Registration(KEY, r"C:\Jev\manifest.json", r"C:\Jev", registry=registry)
    with pytest.raises(control.ControlError) as error:
        registration.apply()
    assert error.value.code == "registry_write"
    assert registry.data == {}


def test_registry_failure_preserves_existing_owned_registration_and_other_values():
    registry = FakeRegistry()
    before = {"": ("manifest", 1), "AsideJevOwner": ("owner", 1), "Other": ("preserve", 1)}
    registry.data[(32, KEY)] = dict(before)
    registration = native_registry.Registration(KEY, "manifest", "owner", registry=registry)
    registry.fail_flush = True
    with pytest.raises(control.ControlError):
        registration.apply()
    assert registry.data[(32, KEY)] == before


def test_registry_external_change_after_preview_is_preserved():
    registry = FakeRegistry()
    registration = native_registry.Registration(KEY, "manifest", "owner", registry=registry)
    registry.data[(32, KEY)] = {"": ("external", 1)}
    with pytest.raises(control.ControlError) as error:
        registration.apply()
    assert error.value.code == "file_changed"
    assert registry.data[(32, KEY)] == {"": ("external", 1)}


def test_windows_setup_preview_and_apply_use_explicit_registry_and_python_mcp(tmp_path, monkeypatch, fake_windows):
    profile = tmp_path / "사용자 & account"
    profile.mkdir()
    root = tmp_path / "설정 ! & ^ (test)"
    monkeypatch.setenv("ASIDE_JEV_CONFIG_DIR", str(root))
    args = dict(extension_id=EXTENSION_ID, profile_dir=profile, native_host_dir=root / "hosts", windows_registry_key=KEY)
    plan = control.setup_installation(**args)
    assert plan["platform"] == "windows"
    assert plan["registry_registration"]["key"] == KEY
    assert not root.exists() and fake_windows.data == {}
    control.setup_installation(**args, apply=True)
    assert (root / "native-host.cmd").exists()
    assert fake_windows.data[(32, KEY)][""][0] == str(root / "hosts" / f"{control.HOST_NAME}.json")
    entry = control.get_status()["aside_mcp_entry"]
    assert entry == {"enabled": True, "transport": "stdio", "command": sys.executable,
                     "args": ["-I", "-X", "utf8", str(root / "mcp-entry.py")], "env": {}}
    before = sorted((root / "backups").iterdir())
    control.setup_installation(**args, apply=True)
    assert sorted((root / "backups").iterdir()) == before


def test_generated_windows_python_entry_preserves_framing_and_origin(tmp_path, monkeypatch, fake_windows):
    profile = tmp_path / "profile"
    profile.mkdir()
    root = tmp_path / "고정 경로 &"
    monkeypatch.setenv("ASIDE_JEV_CONFIG_DIR", str(root))
    control.setup_installation(extension_id=EXTENSION_ID, profile_dir=profile, native_host_dir=root / "hosts",
                               windows_registry_key=KEY, apply=True)
    source = io.BytesIO()
    native_host.write_message(source, {"op": "status"})
    environment = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    result = subprocess.run([sys.executable, "-I", "-X", "utf8", str(root / "native-entry.py"), ORIGIN, "--parent-window=42"],
                            input=source.getvalue(), capture_output=True, env=environment, timeout=15, check=True)
    response = native_host.read_message(io.BytesIO(result.stdout))
    assert response["ok"] and response["status"]["enabled"] is False
    assert not result.stderr


def test_windows_registry_failure_rolls_back_installed_files(tmp_path, fake_windows):
    profile = tmp_path / "profile"
    profile.mkdir()
    root = tmp_path / "config"
    settings = profile / "settings.json"
    settings.write_bytes(b'{"keep":true}')
    key_file = root / "api.env"
    fake_windows.fail_value = ""
    with pytest.raises(control.ControlError) as error:
        control.setup_installation(extension_id=EXTENSION_ID, profile_dir=profile, native_host_dir=tmp_path / "hosts",
                                   windows_registry_key=KEY, root=root, apply=True,
                                   extra_updates=[(settings, b'{"keep":true,"mcp":{}}', 0o600), (key_file, b"fixture", 0o600)],
                                   expected_files={settings: b'{"keep":true}', key_file: None})
    assert error.value.code == "registry_write"
    assert fake_windows.data == {}
    assert not (root / "config.json").exists()
    assert not (root / "native-host.cmd").exists()
    assert not (tmp_path / "hosts" / f"{control.HOST_NAME}.json").exists()
    assert settings.read_bytes() == b'{"keep":true}'
    assert not key_file.exists()
    assert list((root / "backups").glob("*.json"))


def test_setup_precondition_detects_external_change_before_any_install_write(tmp_path, fake_windows):
    profile = tmp_path / "profile"
    profile.mkdir()
    root = tmp_path / "config"
    settings = profile / "settings.json"
    settings.write_bytes(b"changed externally")
    with pytest.raises(control.ControlError) as error:
        control.setup_installation(extension_id=EXTENSION_ID, profile_dir=profile, native_host_dir=tmp_path / "hosts",
                                   windows_registry_key=KEY, root=root, apply=True,
                                   extra_updates=[(settings, b"new settings", 0o600)], expected_files={settings: b"old settings"})
    assert error.value.code == "file_changed"
    assert settings.read_bytes() == b"changed externally"
    assert not (root / "config.json").exists() and fake_windows.data == {}


def test_extra_file_failure_prevents_registration_and_rolls_back(tmp_path, monkeypatch, fake_windows):
    profile = tmp_path / "profile"
    profile.mkdir()
    root = tmp_path / "config"
    extra = root / "extension" / "manifest.json"
    original_write = control._atomic_write
    def fail_extra(path, data, **kwargs):
        if path == extra:
            raise PermissionError("fixture failure")
        original_write(path, data, **kwargs)
    monkeypatch.setattr(control, "_atomic_write", fail_extra)
    with pytest.raises(control.ControlError) as error:
        control.setup_installation(extension_id=EXTENSION_ID, profile_dir=profile, native_host_dir=tmp_path / "hosts",
                                   windows_registry_key=KEY, root=root, apply=True,
                                   extra_updates=[(extra, b"{}", 0o600)])
    assert error.value.code == "write_failed"
    assert not (root / "config.json").exists() and fake_windows.data == {}


def test_preview_returns_canonical_mcp_entry_and_extra_targets_without_writing(tmp_path, fake_windows):
    profile = tmp_path / "profile"
    profile.mkdir()
    root = tmp_path / "config"
    extra = profile / "settings.json"
    plan = control.setup_installation(extension_id=EXTENSION_ID, profile_dir=profile, native_host_dir=tmp_path / "hosts",
                                      windows_registry_key=KEY, root=root,
                                      extra_updates=[(extra, b"{}", 0o600)], expected_files={extra: None})
    assert str(extra) in plan["files"]
    assert plan["aside_mcp_entry"]["args"] == ["-I", "-X", "utf8", str(root / "mcp-entry.py")]
    assert not extra.exists() and not root.exists()


def test_extra_updates_cannot_replace_internal_installation_targets(tmp_path, fake_windows):
    profile = tmp_path / "profile"
    profile.mkdir()
    root = tmp_path / "config"
    with pytest.raises(control.ControlError) as error:
        control.setup_installation(extension_id=EXTENSION_ID, profile_dir=profile, native_host_dir=tmp_path / "hosts",
                                   windows_registry_key=KEY, root=root, extra_updates=[(root / "config.json", b"{}", 0o600)])
    assert error.value.code == "input"
    assert not root.exists()


def test_windows_setup_requires_registry_even_in_preview(tmp_path, fake_windows):
    profile = tmp_path / "profile"
    profile.mkdir()
    with pytest.raises(control.ControlError) as error:
        control.setup_installation(extension_id=EXTENSION_ID, profile_dir=profile, native_host_dir=tmp_path / "hosts")
    assert error.value.code == "registry_target"


@pytest.mark.parametrize("apply", [False, True])
@pytest.mark.parametrize("folder", ["%PATH%", "literal%percent", "%UNKNOWN_TEST_VAR%"])
def test_windows_launcher_percent_path_is_rejected_before_any_write(tmp_path, fake_windows, apply, folder):
    profile = tmp_path / "profile"
    profile.mkdir()
    root = tmp_path / folder / "config"
    hosts = tmp_path / "hosts"
    with pytest.raises(control.ControlError) as error:
        control.setup_installation(extension_id=EXTENSION_ID, profile_dir=profile, native_host_dir=hosts,
                                   root=root, windows_registry_key=KEY, apply=apply)
    assert error.value.code == "launcher_path"
    assert "--config-dir" in str(error.value)
    assert not root.parent.exists() and not hosts.exists() and not fake_windows.data


@pytest.mark.parametrize("path", [r"\\server\share\profile", r"\\?\C:\profile", r"C:\profile\file:secret",
                                  r"C:\profile\NUL.txt", "C:\\profile\\trailing. ", r"relative\profile"])
def test_windows_paths_reject_network_devices_and_aliases(path):
    with pytest.raises(control.ControlError):
        native_platform.validate_windows_path(path)


def test_windows_paths_and_launcher_preserve_unicode_and_literal_metacharacters():
    python = r"C:\사용자 & 개발\%PATH% ! ^ (test)\python.exe"
    native_platform.validate_windows_path(python)
    content = native_platform.windows_launcher(python, native=True).decode("utf-8")
    assert "setlocal DisableDelayedExpansion\r\n" in content
    assert '"C:\\사용자 & 개발\\%%PATH%% ! ^ (test)\\python.exe" -I -X utf8 "%~dp0native-entry.py" "%~1"' in content
    assert "%*" not in content and "powershell" not in content and "-EncodedCommand" not in content
    for helper in (native_platform.windows_entry(native=True), native_platform.windows_entry(native=False), native_platform.windows_status_entry()):
        compile(helper, "generated_helper", "exec")


def test_reparse_attribute_is_rejected_independently_of_symlink_mode(tmp_path, monkeypatch):
    target = tmp_path / "junction"
    target.mkdir()
    original = Path.lstat
    def lstat(path):
        result = original(path)
        if path == target:
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        return result
    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(control.ControlError) as error:
        control._check_path(target / "file")
    assert error.value.code == "unsafe_path"


@pytest.mark.skipif(os.name != "nt", reason="Windows Win32 파일 핸들과 cmd.exe의 실제 실행은 Windows에서 검증")
def test_real_windows_safe_files_lock_and_framed_wrapper(tmp_path, monkeypatch, fake_windows):
    profile = tmp_path / "한글 계정"
    profile.mkdir()
    root = tmp_path / "유니코드 ! & ^ (test)"
    monkeypatch.setenv("ASIDE_JEV_CONFIG_DIR", str(root))
    control.setup_installation(extension_id=EXTENSION_ID, profile_dir=profile, native_host_dir=root / "hosts",
                               windows_registry_key=KEY, apply=True)
    with control._lock(root):
        with pytest.raises(control.ControlError, match="진행 중"):
            with control._lock(root):
                pass
    framed = io.BytesIO()
    native_host.write_message(framed, {"op": "status"})
    result = subprocess.run([str(root / "native-host.cmd"), ORIGIN, "--parent-window=0"],
                            input=framed.getvalue(), capture_output=True, timeout=15, check=False)
    # 임시 fixture 호스트의 실패 원인을 다음 Windows CI에서도 확인할 수 있게 한다.
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")[-2000:]
    assert native_host.read_message(io.BytesIO(result.stdout))["status"]["enabled"] is False
    # cmd의 콘솔 코드 페이지와 별개로, 캡처된 Python 텍스트 출력도 UTF-8이어야 한다.
    status = subprocess.run([str(root / "status-host.cmd")], stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=15, check=False)
    assert status.returncode == 0, status.stderr.decode("utf-8", errors="replace")[-2000:]
    assert json.loads(status.stdout.decode("utf-8"))["profile_label"] == profile.name
    outside = tmp_path / "outside"
    outside.write_text("untouched")
    os.link(outside, profile / "AGENTS.md")
    with pytest.raises(control.ControlError):
        control._read(profile / "AGENTS.md")
    assert outside.read_text() == "untouched"
