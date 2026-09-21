import argparse
import json
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import sys

import pytest

from aside_jev import extension_control as control
from aside_jev import installer


@pytest.fixture
def installation(tmp_path, monkeypatch, keychain_store):
    if sys.platform not in ('darwin', 'win32'):
        monkeypatch.setattr(installer.sys, 'platform', 'darwin')
    if sys.platform == 'win32':
        monkeypatch.setattr(control.native_registry, 'prepare_registration', lambda *a: SimpleNamespace(apply=lambda: None))
    profile = tmp_path / 'Aside 계정 with spaces'
    profile.mkdir()
    original = {'theme': 'dark', 'mcp': {'servers': {'keep-me': {'command': 'example'}}, 'inventories': {'keep': True}}}
    (profile / 'settings.json').write_text(json.dumps(original))
    args = argparse.Namespace(lang='en', config_dir=str(tmp_path / 'config'), profile_dir=str(profile),
                              native_host_dir=str(tmp_path / 'hosts'), windows_registry_key=(r'Software\AsideJevTest\NativeMessagingHosts\com.aside_jev.control' if sys.platform == 'win32' else None),
                              env_file=None, dry_run=False, yes=True)
    for name in control.KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('ASIDE_JEV_CONFIG_DIR', args.config_dir)
    return args, profile, original


def test_assets_have_stable_identity_and_both_languages():
    assets = installer.extension_files()
    assert installer.extension_id(assets) == 'pendehmejnpgceflngbnbpagpodiiemg'
    assert '_locales/en/messages.json' in assets and '_locales/ko/messages.json' in assets
    assert set(installer.MESSAGES['en']) == set(installer.MESSAGES['ko'])


def test_discovery_does_not_read_account_credentials(tmp_path):
    root = tmp_path / '.aside' / 'u'
    for name in ('0', 'u2', 'not-an-account'):
        (root / name).mkdir(parents=True)
        (root / name / 'settings.json').write_text('{}')
    (tmp_path / '.aside' / 'accounts.json').write_text('not readable as JSON')
    assert [p.name for p in installer.discover_profiles(tmp_path)] == ['0', 'u2']


def test_preview_writes_nothing(installation, capsys):
    args, profile, original = installation
    args.dry_run = True
    args.yes = False
    assert installer.setup(args) == 0
    assert not Path(args.config_dir).exists()
    assert not Path(args.native_host_dir).exists()
    assert json.loads((profile / 'settings.json').read_text()) == original
    assert 'Preview only' in capsys.readouterr().out


def test_install_and_repeat_preserve_other_mcp_and_settings(installation):
    args, profile, original = installation
    assert installer.setup(args) == 0
    settings = json.loads((profile / 'settings.json').read_text())
    assert settings['theme'] == 'dark'
    assert settings['mcp']['servers']['keep-me'] == original['mcp']['servers']['keep-me']
    assert settings['mcp']['inventories'] == {'keep': True}
    entry = settings['mcp']['servers']['aside-jev']
    assert entry['enabled'] and entry['transport'] == 'stdio'
    entry_path = entry['args'][-1] if sys.platform == 'win32' else entry['command']
    assert Path(entry_path).parent == Path(args.config_dir)
    assert (Path(args.config_dir) / 'extension' / 'manifest.json').exists()
    assert control.get_status()['enabled'] is False
    assert control.get_status()['key_status'] == 'missing'
    assert control.get_status()['mcp_registration'] == 'configured'
    assert list((Path(args.config_dir) / 'backups').glob('*.json'))
    assert installer.setup(args) == 0
    assert json.loads((profile / 'settings.json').read_text()) == settings


def test_no_silent_replacement_of_other_jev_connection(installation):
    args, profile, original = installation
    original['mcp']['servers']['aside-jev'] = {'command': 'someone-elses-setup'}
    (profile / 'settings.json').write_text(json.dumps(original))
    with pytest.raises(control.ControlError, match='different setup'):
        installer.setup(args)
    assert not Path(args.config_dir).exists()


@pytest.mark.parametrize('bad', [None, b'[]', b'broken', b'{"mcp":[]}', b'{"mcp":{"servers":null}}'])
def test_invalid_settings_fail_closed(bad):
    with pytest.raises(control.ControlError):
        installer.merge_mcp(bad, {}, locale='en')


def test_cancel_does_not_save_secret_or_setup(installation, monkeypatch, capsys):
    args, profile, original = installation
    args.yes = False
    monkeypatch.setattr(installer.sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr(installer.getpass, 'getpass', lambda _: 'test-only-not-a-real-key')
    monkeypatch.setattr('builtins.input', lambda _: 'n')
    installer.setup(args)
    assert not Path(args.config_dir).exists()
    assert 'test-only-not-a-real-key' not in capsys.readouterr().out
    assert json.loads((profile / 'settings.json').read_text()) == original


def test_changed_settings_during_review_are_not_overwritten(installation, monkeypatch):
    args, profile, original = installation
    args.yes = False
    monkeypatch.setattr(installer.sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr(installer.getpass, 'getpass', lambda _: '')
    def confirm(_):
        (profile / 'settings.json').write_text('{"changed": true}')
        return 'y'
    monkeypatch.setattr('builtins.input', confirm)
    with pytest.raises(control.ControlError) as error:
        installer.setup(args)
    assert error.value.code == 'file_changed'
    assert not Path(args.config_dir).exists()
    assert json.loads((profile / 'settings.json').read_text()) == {'changed': True}


def test_existing_unowned_extension_is_preserved(installation):
    args, _, _ = installation
    path = Path(args.config_dir) / 'extension'
    path.mkdir(parents=True)
    (path / 'mine.txt').write_text('mine')
    with pytest.raises(control.ControlError) as error:
        installer.setup(args)
    assert error.value.code == 'assets_conflict'
    assert (path / 'mine.txt').read_text() == 'mine'


def test_korean_preview(installation, capsys):
    args, _, _ = installation
    args.lang = 'ko'
    args.dry_run = True
    installer.setup(args)
    assert '미리보기입니다' in capsys.readouterr().out


def test_explicit_missing_key_file_does_not_install(installation):
    args, _, _ = installation
    args.env_file = str(Path(args.config_dir).parent / 'missing.env')
    with pytest.raises(control.ControlError) as error:
        installer.setup(args)
    assert error.value.code == 'key_file'
    assert not Path(args.config_dir).exists()


def test_reject_shell_separator_in_hidden_key(installation, monkeypatch):
    args, _, _ = installation
    args.yes = False
    monkeypatch.setattr(installer.sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr(installer.getpass, 'getpass', lambda _: 'invalid;key')
    with pytest.raises(control.ControlError) as error:
        installer.setup(args)
    assert error.value.code == 'key_format'
    assert not Path(args.config_dir).exists()


def test_environment_key_survives_new_browser_process(installation, monkeypatch, capsys):
    args, _, _ = installation
    monkeypatch.setenv('TYPESAFE_API_KEY', 'test-only-not-a-real-key')
    installer.setup(args)
    monkeypatch.delenv('TYPESAFE_API_KEY')
    assert control.get_status()['live_available']
    assert 'test-only-not-a-real-key' not in capsys.readouterr().out


def test_windows_discovery_never_invents_missing_registry_parent(monkeypatch):
    class Registry:
        HKEY_CURRENT_USER = 1
        HKEY_LOCAL_MACHINE = 2
        KEY_READ = 4
        KEY_WOW64_32KEY = 8
        KEY_WOW64_64KEY = 16
        @staticmethod
        def OpenKey(*args):
            raise FileNotFoundError()
    monkeypatch.setitem(sys.modules, 'winreg', Registry)
    assert installer.existing_windows_registration() is None


def test_windows_discovery_proposes_only_existing_parent(monkeypatch):
    from contextlib import nullcontext
    class Registry:
        HKEY_CURRENT_USER = 1
        HKEY_LOCAL_MACHINE = 2
        KEY_READ = 4
        KEY_WOW64_32KEY = 8
        KEY_WOW64_64KEY = 16
        @staticmethod
        def OpenKey(hive, key, reserved, access):
            assert key == r'Software\Aside\NativeMessagingHosts'
            return nullcontext()
    monkeypatch.setitem(sys.modules, 'winreg', Registry)
    assert installer.existing_windows_registration().endswith('\\com.aside_jev.control')
