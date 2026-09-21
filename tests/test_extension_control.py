import json
import os
from pathlib import Path
import stat

import pytest

from aside_jev import extension_control as control

EXTENSION_ID = "a" * 32


@pytest.fixture(autouse=True)
def isolated_global_rules(tmp_path, monkeypatch):
    from test_native_platform import isolate_windows_registration
    isolate_windows_registration(monkeypatch)
    monkeypatch.setattr(control, "_legacy_rule_paths", lambda: {"user_home": tmp_path / "global-AGENTS.md"})


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "config"
    profile = tmp_path / "aside" / "account-test"
    hosts = tmp_path / "native-hosts"
    profile.mkdir(parents=True)
    monkeypatch.setenv("ASIDE_JEV_CONFIG_DIR", str(root))
    for name in control.KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    control.setup_installation(extension_id=EXTENSION_ID, profile_dir=profile, native_host_dir=hosts, apply=True)
    return root, profile, hosts


def test_dry_run_has_no_filesystem_writes(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    plan = control.setup_installation(extension_id=EXTENSION_ID, profile_dir=profile, native_host_dir=tmp_path / "hosts", root=tmp_path / "config")
    assert not plan["apply"]
    assert plan["starts_background_service"] is False
    assert sorted(path.name for path in tmp_path.iterdir()) == ["profile"]


def test_setup_manifest_is_scoped_and_default_off(installation):
    root, profile, hosts = installation
    manifest = json.loads((hosts / f"{control.HOST_NAME}.json").read_text(encoding="utf-8"))
    assert manifest["allowed_origins"] == [f"chrome-extension://{EXTENSION_ID}/"]
    assert manifest["path"] == str(root / ("native-host.cmd" if os.name == "nt" else "native-host"))
    assert not (profile / "AGENTS.md").exists()
    if os.name != "nt":
        assert stat.S_IMODE((root / "config.json").stat().st_mode) == 0o600
        assert stat.S_IMODE((root / "native-host").stat().st_mode) == 0o700
    status = control.get_status()
    assert not status["enabled"]
    assert status["enforcement"] == "instructions_only"
    assert status["scope"] == "new_aside_tasks"
    assert status["native_interception"] is False
    assert status["mcp_connected"] is None


def test_on_requires_key_before_any_profile_change(installation):
    root, profile, _ = installation
    original = (root / "config.json").read_bytes()
    with pytest.raises(control.ControlError) as error:
        control.set_enabled(True)
    assert error.value.code == "key_missing"
    assert not (profile / "AGENTS.md").exists()
    assert not (profile / "skills").exists()
    assert (root / "config.json").read_bytes() == original


def test_on_off_preserves_user_rules_and_is_idempotent(installation, monkeypatch):
    root, profile, _ = installation
    agents = profile / "AGENTS.md"
    original = "# 내 규칙\n기존 사용자 지침을 보존한다."
    agents.write_text(original, encoding="utf-8")
    monkeypatch.setenv("TYPESAFE_API_KEY", "sentinel-secret")
    status = control.set_enabled(True)
    assert status["enabled"] and status["instructions_applied"]
    assert "sentinel-secret" not in json.dumps(status)
    assert agents.read_text(encoding="utf-8").startswith(original + "\n")
    skill = profile / "skills" / "user" / "aside-jev" / "SKILL.md"
    assert "MCP `jev_extension_status`" in skill.read_text(encoding="utf-8")
    assert "OFF" in skill.read_text(encoding="utf-8")
    before = agents.read_bytes(), skill.read_bytes(), (root / "config.json").read_bytes(), sorted((root / "backups").iterdir())
    control.set_enabled(True)
    assert before == (agents.read_bytes(), skill.read_bytes(), (root / "config.json").read_bytes(), sorted((root / "backups").iterdir()))
    status = control.set_enabled(False)
    assert not status["enabled"]
    assert agents.read_text(encoding="utf-8") == original
    assert skill.exists()
    control.set_enabled(False)
    assert agents.read_text(encoding="utf-8") == original


def test_duplicate_legacy_blocks_are_migrated_and_backed_up(installation, monkeypatch):
    root, profile, _ = installation
    legacy = f"{control.LEGACY_BEGIN}\nold rules\n{control.LEGACY_END}\n"
    original = "# User\n" + legacy + "Keep this.\n" + legacy
    agents = profile / "AGENTS.md"
    agents.write_text(original, encoding="utf-8")
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake")
    control.set_enabled(True)
    assert agents.read_text(encoding="utf-8").count(control.BEGIN) == 1
    assert control.LEGACY_BEGIN not in agents.read_text(encoding="utf-8")
    assert "Keep this." in agents.read_text(encoding="utf-8")
    assert any(path.read_text(encoding="utf-8") == original for path in (root / "backups").glob("*.bak"))
    control.set_enabled(False)
    assert agents.read_text(encoding="utf-8") == "# User\nKeep this.\n"


def test_damaged_markers_fail_without_truncating_user_text(installation, monkeypatch):
    _, profile, _ = installation
    agents = profile / "AGENTS.md"
    original = "# User\n" + control.LEGACY_BEGIN + "\nUser text after damaged marker\n"
    agents.write_text(original, encoding="utf-8")
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake")
    with pytest.raises(control.ControlError, match="관리 구간"):
        control.set_enabled(True)
    assert agents.read_text(encoding="utf-8") == original


def test_configure_updates_rules_when_enabled_and_off_does_not_install(installation, monkeypatch):
    _, profile, _ = installation
    control.configure(min_confidence=0.8, timeout_s=20)
    assert not (profile / "AGENTS.md").exists()
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake")
    control.set_enabled(True)
    result = control.configure(min_confidence=0.9, timeout_s=30)
    assert result["enabled"]
    assert "0.9" in (profile / "AGENTS.md").read_text(encoding="utf-8")
    assert control.load_runtime_policy() == {"enabled": True, "execution_ready": False, "model": "jev-latest", "min_confidence": 0.9, "timeout_s": 30.0}


@pytest.mark.parametrize("values", [{"min_confidence": float("nan")}, {"min_confidence": True}, {"min_confidence": 1.1}, {"timeout_s": 0}, {"timeout_s": float("inf")}])
def test_invalid_settings_leave_configuration_unchanged(installation, values):
    root, _, _ = installation
    before = (root / "config.json").read_bytes()
    with pytest.raises(control.ControlError):
        control.configure(**values)
    assert (root / "config.json").read_bytes() == before


def test_manual_rule_drift_disables_effective_policy(installation, monkeypatch):
    _, profile, _ = installation
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake")
    control.set_enabled(True)
    agents = profile / "AGENTS.md"
    agents.write_text(agents.read_text(encoding="utf-8").replace("provider는 live", "provider는 mock"))
    status = control.get_status()
    assert status["desired_enabled"] is True
    assert status["enabled"] is False
    assert status["instructions_applied"] is False


def test_transaction_failure_restores_original_rules_and_config(installation, monkeypatch):
    root, profile, _ = installation
    agents = profile / "AGENTS.md"
    agents.write_text("# Original\n", encoding="utf-8")
    before = (root / "config.json").read_bytes()
    write = control._atomic_write
    def fail_agents_once(path, data, **kwargs):
        if path == agents and control.BEGIN.encode() in data:
            raise OSError("simulated failure secret-value")
        return write(path, data, **kwargs)
    monkeypatch.setattr(control, "_atomic_write", fail_agents_once)
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake")
    with pytest.raises(control.ControlError) as error:
        control.set_enabled(True)
    assert error.value.code == "write_failed"
    assert "secret-value" not in str(error.value)
    assert agents.read_text(encoding="utf-8") == "# Original\n"
    assert (root / "config.json").read_bytes() == before
    assert not (profile / "skills" / "user" / "aside-jev" / "SKILL.md").exists()


def test_unknown_skill_is_not_overwritten(installation, monkeypatch):
    _, profile, _ = installation
    skill = profile / "skills" / "user" / "aside-jev" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("My unrelated skill", encoding="utf-8")
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake")
    with pytest.raises(control.ControlError) as error:
        control.set_enabled(True)
    assert error.value.code == "skill_conflict"
    assert skill.read_text(encoding="utf-8") == "My unrelated skill"


def test_symlinked_agents_cannot_redirect_writes(installation, monkeypatch, tmp_path):
    _, profile, _ = installation
    target = tmp_path / "untouched"
    target.write_text("outside", encoding="utf-8")
    try:
        (profile / "AGENTS.md").symlink_to(target)
    except OSError:
        if os.name == "nt":
            pytest.skip("Windows 심볼릭 링크 생성 권한이 없는 환경")
        raise
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake")
    with pytest.raises(control.ControlError) as error:
        control.set_enabled(True)
    assert error.value.code == "unsafe_path"
    assert target.read_text(encoding="utf-8") == "outside"


def test_symlinked_profile_is_rejected_before_install(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(actual, target_is_directory=True)
    except OSError:
        if os.name == "nt":
            pytest.skip("Windows 심볼릭 링크 생성 권한이 없는 환경")
        raise
    with pytest.raises(control.ControlError):
        control.setup_installation(extension_id=EXTENSION_ID, profile_dir=link, native_host_dir=tmp_path / "hosts", root=tmp_path / "config", apply=True)
    assert not (tmp_path / "config").exists()


def test_safe_env_file_is_loaded_without_printing_or_evaluating(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    profile.mkdir()
    env_file = tmp_path / "keys.env"
    env_file.write_text('# comment\nexport TYPESAFE_API_KEY="key-private" # trailing\n', encoding="utf-8")
    monkeypatch.setenv("ASIDE_JEV_CONFIG_DIR", str(tmp_path / "config"))
    for name in control.KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    control.setup_installation(extension_id=EXTENSION_ID, profile_dir=profile, native_host_dir=tmp_path / "hosts", env_file=env_file, apply=True)
    assert control.get_status()["live_available"]
    assert "key-private" not in json.dumps(control.get_status())
    assert control.load_key_environment()
    assert __import__("os").environ["TYPESAFE_API_KEY"] == "key-private"
    monkeypatch.delenv("TYPESAFE_API_KEY")


@pytest.mark.parametrize("content", [
    'TYPESAFE_API_KEY="$(touch /tmp/not-run)"', 'TYPESAFE_API_KEY=`command`',
    'OTHER_KEY=secret', 'source other.env', 'TYPESAFE_API_KEY=x;echo danger',
])
def test_env_file_rejects_shell_syntax_and_unknown_keys(tmp_path, monkeypatch, content):
    profile = tmp_path / "profile"
    profile.mkdir()
    keyfile = tmp_path / "keys.env"
    keyfile.write_text(content, encoding="utf-8")
    monkeypatch.setenv("ASIDE_JEV_CONFIG_DIR", str(tmp_path / "config"))
    for name in control.KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    control.setup_installation(extension_id=EXTENSION_ID, profile_dir=profile, native_host_dir=tmp_path / "hosts", env_file=keyfile, apply=True)
    assert control.get_status()["key_status"] == "file_error"
    with pytest.raises(control.ControlError) as error:
        control.set_enabled(True)
    assert error.value.code == "key_file"
    assert content not in str(error.value)
    assert not (profile / "AGENTS.md").exists()


def test_reinstall_keeps_enabled_settings_and_rejects_different_profile(installation, monkeypatch, tmp_path):
    root, profile, hosts = installation
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake")
    control.set_enabled(True)
    control.configure(timeout_s=22)
    control.setup_installation(extension_id=EXTENSION_ID, profile_dir=profile, native_host_dir=hosts, apply=True)
    assert control.get_status()["enabled"]
    assert control.get_status()["timeout_s"] == 22
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(control.ControlError) as error:
        control.setup_installation(extension_id=EXTENSION_ID, profile_dir=other, native_host_dir=hosts, apply=True)
    assert error.value.code == "installation_conflict"
    assert not (other / "AGENTS.md").exists()


def test_origin_validation_and_lock_contention(installation):
    root, _, _ = installation
    control.validate_origin(f"chrome-extension://{EXTENSION_ID}/")
    with pytest.raises(control.ControlError) as error:
        control.validate_origin(f"chrome-extension://{'b' * 32}/")
    assert error.value.code == "origin"
    with control._lock(root):
        with pytest.raises(control.ControlError) as error:
            control.configure(timeout_s=20)
    assert error.value.code == "busy"


def test_failure_after_atomic_replace_is_also_rolled_back(installation, monkeypatch):
    root, profile, _ = installation
    agents = profile / "AGENTS.md"
    agents.write_text("Preserve exact original\n", encoding="utf-8")
    original_config = (root / "config.json").read_bytes()
    original_write = control._atomic_write
    def fail_after_replace(path, data, **kwargs):
        original_write(path, data, **kwargs)
        if path == agents and control.BEGIN.encode() in data:
            raise OSError("simulated directory fsync failure")
    monkeypatch.setattr(control, "_atomic_write", fail_after_replace)
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake")
    with pytest.raises(control.ControlError) as error:
        control.set_enabled(True)
    assert error.value.code == "write_failed"
    assert agents.read_text(encoding="utf-8") == "Preserve exact original\n"
    assert (root / "config.json").read_bytes() == original_config


def test_fifo_config_and_hardlinked_agents_are_rejected(installation, monkeypatch, tmp_path):
    import os
    root, profile, _ = installation
    fifo = tmp_path / "fifo"
    if hasattr(os, "mkfifo"):
        os.mkfifo(fifo)
        with pytest.raises(control.ControlError) as error:
            control._read(fifo)
        assert error.value.code == "unsafe_path"
    outside = tmp_path / "outside"
    outside.write_text("do not alter", encoding="utf-8")
    os.link(outside, profile / "AGENTS.md")
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake")
    with pytest.raises(control.ControlError) as error:
        control.set_enabled(True)
    assert error.value.code == "unsafe_path"
    assert outside.read_text(encoding="utf-8") == "do not alter"


def test_installer_does_not_replace_another_native_registration(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    hosts = tmp_path / "hosts"
    hosts.mkdir()
    manifest = hosts / f"{control.HOST_NAME}.json"
    original = json.dumps({"path": "/other/program", "allowed_origins": ["chrome-extension://" + "b" * 32 + "/"]})
    manifest.write_text(original, encoding="utf-8")
    with pytest.raises(control.ControlError) as error:
        control.setup_installation(extension_id=EXTENSION_ID, profile_dir=profile, native_host_dir=hosts, root=tmp_path / "config", apply=True)
    assert error.value.code == "installation_conflict"
    assert manifest.read_text(encoding="utf-8") == original
    assert not (tmp_path / "config").exists()


def test_off_warns_about_global_legacy_rules_without_modifying_them(installation, monkeypatch, tmp_path):
    _, profile, _ = installation
    global_rule = tmp_path / "global-AGENTS.md"
    global_rule.write_text(f"# User global\n{control.LEGACY_BEGIN}\nold global requirement\n{control.LEGACY_END}\n", encoding="utf-8")
    before = global_rule.read_bytes()
    monkeypatch.setattr(control, "_legacy_rule_paths", lambda: {"user_home": global_rule})
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake")
    control.set_enabled(True)
    status = control.set_enabled(False)
    assert not status["enabled"]
    assert status["legacy_global_rules"] == ["user_home"]
    assert status["warnings"] and "OFF" in status["warnings"][0]
    assert global_rule.read_bytes() == before
    assert control.BEGIN not in (profile / "AGENTS.md").read_text(encoding="utf-8")
