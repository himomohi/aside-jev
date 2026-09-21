import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from aside_jev import credentials, extension_control as control, installer, keychain

ACCOUNT = "a" * 64
SECRET = "fixture-not-a-real-api-key"


@pytest.mark.parametrize("secret", ["", " ", "with space", "line\nbreak", "nul\0byte", "한글", "x" * 4097, None, 42])
def test_invalid_key_never_reaches_storage(secret, keychain_store):
    with pytest.raises(control.ControlError):
        keychain.replace_verified(ACCOUNT, secret)
    assert not keychain_store.calls


def test_account_is_stable_and_scoped(tmp_path):
    first = keychain.account_id(tmp_path / "one", tmp_path / "profile")
    assert len(first) == 64 and first == keychain.account_id(tmp_path / "one", tmp_path / "profile")
    assert first != keychain.account_id(tmp_path / "two", tmp_path / "profile")
    assert first != keychain.account_id(tmp_path / "one", tmp_path / "other-profile")


@pytest.mark.parametrize("code", [-128, -25293, -25308, -25291])
def test_errors_have_safe_actionable_codes(code):
    with pytest.raises(control.ControlError) as error:
        keychain._check(code)
    assert error.value.code.startswith("keychain_")
    assert "plaintext fallback" in str(error.value)


def test_replace_verifies_and_same_value_does_not_write(keychain_store):
    keychain.replace_verified(ACCOUNT, SECRET)
    assert keychain_store.values[ACCOUNT] == SECRET
    assert [name for name, _ in keychain_store.calls] == ["get", "set", "get"]
    keychain_store.calls.clear()
    keychain.replace_verified(ACCOUNT, SECRET)
    assert keychain_store.calls == [("get", ACCOUNT)]


@pytest.mark.parametrize("old", [None, "previous-fixture-key"])
def test_failed_readback_restores_previous_key(old, keychain_store, monkeypatch):
    if old is not None:
        keychain_store.values[ACCOUNT] = old
    original_get = keychain_store.get
    calls = 0
    def bad_read(account, **kwargs):
        nonlocal calls
        calls += 1
        return "wrong-result" if calls == 2 else original_get(account, **kwargs)
    monkeypatch.setattr(keychain_store, "get", bad_read)
    with pytest.raises(control.ControlError) as error:
        keychain.replace_verified(ACCOUNT, SECRET)
    assert error.value.code == "keychain_verify"
    assert keychain_store.values.get(ACCOUNT) == old


def test_denied_read_does_not_attempt_write(keychain_store, monkeypatch):
    def denied(*args, **kwargs):
        raise control.ControlError("keychain_access", "Denied")
    monkeypatch.setattr(keychain_store, "get", denied)
    with pytest.raises(control.ControlError):
        keychain.replace_verified(ACCOUNT, SECRET)
    assert not keychain_store.calls


def test_keychain_lookup_never_falls_back_to_env_or_file(keychain_store, monkeypatch, tmp_path):
    monkeypatch.setenv("TYPESAFE_API_KEY", "stale-fixture-key")
    path = tmp_path / "api.env"
    path.write_text("TYPESAFE_API_KEY=file-fixture-key\n")
    config = {"credential_store": "keychain", "keychain_account": ACCOUNT, "env_file": str(path)}
    assert control._key_values(config) == {}
    keychain_store.values[ACCOUNT] = SECRET
    assert control._key_values(config) == {"TYPESAFE_API_KEY": SECRET}


@pytest.fixture
def mac_installation(tmp_path, monkeypatch, keychain_store):
    if os.name == "nt":
        pytest.skip("macOS credential/file migration; Windows keeps env-file storage")
    base = tmp_path.resolve()  # /var is a symlink on macOS.
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(control, "_legacy_rule_paths", lambda: {})
    for name in control.KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    root, profile, hosts = base / "config", base / "profile", base / "hosts"
    profile.mkdir()
    (profile / "settings.json").write_text('{"theme":"keep","mcp":{"servers":{}}}')
    monkeypatch.setenv("ASIDE_JEV_CONFIG_DIR", str(root))
    # Asset layout is covered by the existing installer tests, not duplicated here.
    monkeypatch.setattr(installer, "extension_files", lambda: {"manifest.json": b'{"key":"dGVzdA=="}'})
    args = SimpleNamespace(lang="en", config_dir=str(root), profile_dir=str(profile), native_host_dir=str(hosts),
                           windows_registry_key=None, env_file=None, dry_run=False, yes=True)
    return args, root, profile, hosts


def install_legacy(parts, *, external=False):
    args, root, profile, hosts = parts
    root.mkdir(exist_ok=True)
    source = root.parent / "external.env" if external else root / "api.env"
    source.write_text("TYPESAFE_API_KEY=" + SECRET + "\n")
    control.setup_installation(extension_id=installer.extension_id(installer.extension_files()), profile_dir=profile,
                               native_host_dir=hosts, env_file=source, root=root, apply=True)
    return source


def assert_no_plaintext(root, secret=SECRET):
    for path in root.rglob("*"):
        if path.is_file():
            assert secret.encode() not in path.read_bytes(), path.name


def test_setup_defaults_to_keychain_without_plaintext(mac_installation, keychain_store, monkeypatch, capsys):
    args, root, profile, _ = mac_installation
    monkeypatch.setenv("TYPESAFE_API_KEY", SECRET)
    assert installer.setup(args) == 0
    account = keychain.account_id(root, profile)
    assert keychain_store.values[account] == SECRET
    config = control._load_config(root)
    assert config["credential_store"] == "keychain" and config["env_file"] is None
    assert not (root / "api.env").exists()
    assert_no_plaintext(root)
    assert SECRET not in capsys.readouterr().out
    monkeypatch.delenv("TYPESAFE_API_KEY")
    assert control.load_key_environment()
    assert os.environ["TYPESAFE_API_KEY"] == SECRET


def test_reinstall_does_not_overwrite_key_with_stale_env(mac_installation, keychain_store, monkeypatch):
    args, root, profile, _ = mac_installation
    monkeypatch.setenv("TYPESAFE_API_KEY", SECRET)
    installer.setup(args)
    monkeypatch.setenv("TYPESAFE_API_KEY", "stale-fixture-key")
    installer.setup(args)
    assert keychain_store.values[keychain.account_id(root, profile)] == SECRET


def test_preview_and_cancel_never_write_keychain(mac_installation, keychain_store, monkeypatch):
    args, root, _, _ = mac_installation
    monkeypatch.setenv("TYPESAFE_API_KEY", SECRET)
    args.dry_run = True
    installer.setup(args)
    assert not root.exists() and not keychain_store.calls
    args.dry_run, args.yes = False, False
    monkeypatch.setattr("builtins.input", lambda _: "n")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    installer.setup(args)
    assert not root.exists() and not keychain_store.calls


@pytest.mark.parametrize("guided", [False, True])
def test_migration_verifies_then_removes_only_managed_file(guided, mac_installation, keychain_store, monkeypatch):
    args, root, profile, _ = mac_installation
    source = install_legacy(mac_installation)
    monkeypatch.setenv("TYPESAFE_API_KEY", "unrelated-shell-key")
    if guided:
        installer.setup(args)
    else:
        credentials.manage("migrate")
    assert not source.exists()
    assert keychain_store.values[keychain.account_id(root, profile)] == SECRET
    assert control._load_config(root)["env_file"] is None
    assert_no_plaintext(root)


def test_external_import_is_not_deleted(mac_installation, keychain_store):
    args, root, profile, _ = mac_installation
    source = install_legacy(mac_installation, external=True)
    args.env_file = str(source)
    installer.setup(args)
    assert source.read_text() == "TYPESAFE_API_KEY=" + SECRET + "\n"
    assert keychain_store.values[keychain.account_id(root, profile)] == SECRET
    assert_no_plaintext(root)


@pytest.mark.parametrize("guided", [False, True])
def test_keychain_denial_preserves_old_config_and_key_file(guided, mac_installation, keychain_store, monkeypatch):
    args, root, _, _ = mac_installation
    source = install_legacy(mac_installation)
    original = (root / "config.json").read_bytes()
    def denied(*args, **kwargs):
        raise control.ControlError("keychain_access", "Denied")
    monkeypatch.setattr(keychain_store, "get", denied)
    with pytest.raises(control.ControlError) as error:
        installer.setup(args) if guided else credentials.manage("migrate")
    assert error.value.code == "keychain_access"
    assert (root / "config.json").read_bytes() == original
    assert SECRET in source.read_text()
    assert not keychain_store.values
    assert_no_plaintext(root / "backups")


def test_status_uses_only_metadata(mac_installation, keychain_store, monkeypatch):
    args, _, _, _ = mac_installation
    monkeypatch.setenv("TYPESAFE_API_KEY", SECRET)
    installer.setup(args)
    def forbidden(*args, **kwargs):
        raise AssertionError("status must not request secret bytes")
    monkeypatch.setattr(keychain_store, "get", forbidden)
    assert control.get_status()["key_status"] == "configured"
    assert credentials.manage("status")["key_status"] == "configured"


def test_rotation_deletion_and_denial_clear_stale_process_keys(mac_installation, keychain_store, monkeypatch):
    args, root, profile, _ = mac_installation
    monkeypatch.setenv("TYPESAFE_API_KEY", SECRET)
    installer.setup(args)
    account = keychain.account_id(root, profile)
    assert control.load_key_environment()
    keychain_store.values[account] = "rotated-fixture-key"
    monkeypatch.setenv("TYPESAFEAI_API_KEY", "stale-alias")
    assert control.load_key_environment()
    assert os.environ["TYPESAFE_API_KEY"] == "rotated-fixture-key"
    assert "TYPESAFEAI_API_KEY" not in os.environ
    del keychain_store.values[account]
    assert not control.load_key_environment()
    assert all(name not in os.environ for name in control.KEY_NAMES)
    monkeypatch.setenv("TYPESAFE_API_KEY", "stale-fixture-key")
    def denied(*args, **kwargs):
        raise control.ControlError("keychain_access", "Denied")
    monkeypatch.setattr(keychain_store, "get", denied)
    with pytest.raises(control.ControlError):
        control.load_key_environment()
    assert all(name not in os.environ for name in control.KEY_NAMES)


def test_delete_is_scoped_idempotent_and_does_not_delete_settings(mac_installation, keychain_store, monkeypatch):
    args, root, profile, _ = mac_installation
    monkeypatch.setenv("TYPESAFE_API_KEY", SECRET)
    installer.setup(args)
    keychain_store.values[ACCOUNT] = "other-installation-key"
    settings = (root / "config.json").read_bytes()
    assert credentials.manage("delete")["deleted"] is True
    assert credentials.manage("delete")["deleted"] is False
    assert keychain_store.values == {ACCOUNT: "other-installation-key"}
    assert (root / "config.json").read_bytes() == settings
    assert (profile / "settings.json").exists()


@pytest.mark.parametrize("invalid", [{"credential_store":"bogus"}, {"keychain_account":"b"*64}, {"env_file":"/tmp/legacy.env"}])
def test_invalid_keychain_config_is_rejected(invalid, mac_installation):
    args, root, _, _ = mac_installation
    installer.setup(args)
    config = control._load_config(root)
    config.update(invalid)
    (root / "config.json").write_text(json.dumps(config))
    with pytest.raises(control.ControlError) as error:
        control._load_config(root)
    assert error.value.code == "configuration"


def test_no_silent_downgrade_to_plaintext(mac_installation):
    args, root, profile, hosts = mac_installation
    installer.setup(args)
    with pytest.raises(control.ControlError) as error:
        control.setup_installation(extension_id=installer.extension_id(installer.extension_files()), profile_dir=profile,
                                   native_host_dir=hosts, root=root, apply=True)
    assert error.value.code == "installation_conflict"
    assert control._load_config(root)["credential_store"] == "keychain"


def test_conflicting_aliases_are_not_guessed(mac_installation):
    _, root, _, _ = mac_installation
    source = install_legacy(mac_installation)
    source.write_text("TYPESAFE_API_KEY=one\nTYPESAFEAI_API_KEY=two\n")
    with pytest.raises(control.ControlError) as error:
        credentials.manage("migrate")
    assert error.value.code == "key_ambiguous"
    assert control._load_config(root).get("credential_store") != "keychain"


def test_source_changed_during_review_stops_before_keychain(mac_installation, keychain_store, monkeypatch):
    args, _, _, _ = mac_installation
    source = install_legacy(mac_installation)
    args.yes = False
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    def confirm(_):
        source.write_text("TYPESAFE_API_KEY=changed-fixture\n")
        return "y"
    monkeypatch.setattr("builtins.input", confirm)
    with pytest.raises(control.ControlError) as error:
        installer.setup(args)
    assert error.value.code == "file_changed"
    assert not keychain_store.calls
