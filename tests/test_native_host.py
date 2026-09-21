import io
import json
import os
from pathlib import Path
import struct
import subprocess

import pytest

from aside_jev import extension_control as control, native_host

EXTENSION_ID = "a" * 32
ORIGIN = f"chrome-extension://{EXTENSION_ID}/"


@pytest.fixture(autouse=True)
def isolated_global_rules(tmp_path, monkeypatch):
    from test_native_platform import isolate_windows_registration
    isolate_windows_registration(monkeypatch)
    monkeypatch.setattr(control, "_legacy_rule_paths", lambda: {"user_home": tmp_path / "global-AGENTS.md"})


@pytest.fixture
def installed(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    profile.mkdir()
    monkeypatch.setenv("ASIDE_JEV_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("TYPESAFE_API_KEY", "native-test-private")
    control.setup_installation(extension_id=EXTENSION_ID, profile_dir=profile, native_host_dir=tmp_path / "hosts", apply=True)
    return profile


def frame(value):
    payload = json.dumps(value).encode()
    return struct.pack("=I", len(payload)) + payload


def invoke(value, *, origin=ORIGIN):
    destination = io.BytesIO()
    assert native_host.serve(origin, stdin=io.BytesIO(frame(value)), stdout=destination) == 0
    data = destination.getvalue()
    length = struct.unpack("=I", data[:4])[0]
    assert len(data[4:]) == length
    return json.loads(data[4:])


def test_native_status_and_toggle_contract(installed):
    status = invoke({"op": "status"})
    assert status["ok"] is True
    assert status["status"]["enabled"] is False
    assert "native-test-private" not in json.dumps(status)
    assert invoke({"op": "set_enabled", "enabled": True})["status"]["instructions_applied"]
    assert invoke({"op": "configure", "min_confidence": 0.9, "timeout_s": 30})["status"]["min_confidence"] == 0.9
    assert invoke({"op": "set_enabled", "enabled": False})["status"]["enabled"] is False


def test_wrong_origin_has_no_profile_effect(installed):
    result = invoke({"op": "set_enabled", "enabled": True}, origin="chrome-extension://" + "b" * 32 + "/")
    assert result["error"]["code"] == "origin"
    assert not (installed / "AGENTS.md").exists()


@pytest.mark.parametrize("message", [
    {"op": "status", "profile_dir": "/tmp/other"},
    {"op": "set_enabled", "enabled": "true"},
    {"op": "configure", "model": "other"},
    {"op": "configure", "min_confidence": None},
    {"op": "configure", "timeout_s": float("nan")},
    {"op": "run", "command": "arbitrary"},
])
def test_unrecognized_operations_and_fields_are_rejected(installed, message):
    assert invoke(message)["ok"] is False
    assert not (installed / "AGENTS.md").exists()


@pytest.mark.parametrize("payload", [b"x", struct.pack("=I", 0), struct.pack("=I", 131073), struct.pack("=I", 4) + b"{}", struct.pack("=I", 1) + b"x"])
def test_corrupt_and_oversize_frames_return_framed_errors(payload):
    destination = io.BytesIO()
    native_host.serve(ORIGIN, stdin=io.BytesIO(payload), stdout=destination)
    result = native_host.read_message(io.BytesIO(destination.getvalue()))
    assert result["ok"] is False


def test_duplicate_fields_are_rejected():
    payload = b'{"op":"status","op":"set_enabled"}'
    with pytest.raises(control.ControlError):
        native_host.read_message(io.BytesIO(struct.pack("=I", len(payload)) + payload))


def test_exactly_one_request_is_handled_per_process(installed):
    source = io.BytesIO(frame({"op": "status"}) + frame({"op": "set_enabled", "enabled": True}))
    output = io.BytesIO()
    native_host.serve(ORIGIN, stdin=source, stdout=output)
    assert native_host.read_message(io.BytesIO(output.getvalue()))["status"]["enabled"] is False
    assert source.read()
    assert not (installed / "AGENTS.md").exists()


def test_unexpected_error_details_are_not_returned(installed, monkeypatch):
    def fail():
        raise RuntimeError("sensitive provider body native-test-private")
    monkeypatch.setattr(control, "get_status", fail)
    result = invoke({"op": "status"})
    assert result["error"]["code"] == "internal"
    assert "sensitive" not in json.dumps(result)
    assert "native-test-private" not in json.dumps(result)


def test_generated_native_wrapper_runs_cli_with_one_framed_response(installed, tmp_path):
    environment = dict(os.environ)
    environment["HOME"] = str(tmp_path)
    environment["USERPROFILE"] = str(tmp_path)
    wrapper = Path(environment["ASIDE_JEV_CONFIG_DIR"]) / ("native-host.cmd" if os.name == "nt" else "native-host")
    result = subprocess.run(
        [str(wrapper), ORIGIN], input=frame({"op": "status"}),
        capture_output=True, env=environment, cwd=tmp_path, timeout=10, check=True,
    )
    response = native_host.read_message(io.BytesIO(result.stdout))
    assert response["ok"] is True
    assert response["status"]["enabled"] is False
    assert response["status"]["enforcement"] == "instructions_only"
    assert response["status"]["legacy_global_rules"] == []
    assert not result.stderr
    assert b"native-test-private" not in result.stdout
    assert not (installed / "AGENTS.md").exists()


@pytest.mark.parametrize("arguments,valid", [
    ([ORIGIN], True), ([ORIGIN, "--parent-window=0"], True),
    ([ORIGIN, "--parent-window=123456"], True),
    ([ORIGIN, "--other=value"], False), ([ORIGIN, "--parent-window=-1"], False),
    ([ORIGIN, "--parent-window=1", "extra"], False), (["untrusted"], False), ([], False),
])
def test_windows_native_arguments_allow_only_origin_and_optional_parent(arguments, valid):
    assert native_host.origin_from_arguments(arguments) == (ORIGIN if valid else "")


def test_cli_native_host_accepts_browser_parent_window(installed, tmp_path):
    import sys
    result = subprocess.run([sys.executable, "-m", "aside_jev.cli", "native-host", ORIGIN, "--parent-window=0"],
                            input=frame({"op": "status"}), capture_output=True, cwd=tmp_path, timeout=10, check=True)
    assert native_host.read_message(io.BytesIO(result.stdout))["ok"] is True
    assert not result.stderr


def test_windows_standard_pipes_are_switched_to_binary(monkeypatch):
    import sys
    from types import SimpleNamespace

    class Pipe(io.BytesIO):
        def __init__(self, descriptor, data=b""):
            super().__init__(data)
            self.descriptor = descriptor

        def fileno(self):
            return self.descriptor

    calls = []
    source, output = Pipe(0, frame({"op": "status"})), Pipe(1)
    monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(setmode=lambda fd, mode: calls.append((fd, mode))))
    monkeypatch.setattr(native_host, "os", SimpleNamespace(name="nt", O_BINARY=32768))
    monkeypatch.setattr(native_host, "sys", SimpleNamespace(stdin=SimpleNamespace(buffer=source), stdout=SimpleNamespace(buffer=output)))
    monkeypatch.setattr(native_host, "dispatch", lambda origin, message: {"ok": True, "label": "한글\n줄바꿈"})
    assert native_host.serve(ORIGIN) == 0
    assert calls == [(0, 32768), (1, 32768)]
    assert native_host.read_message(io.BytesIO(output.getvalue())) == {"ok": True, "label": "한글\n줄바꿈"}


def test_injected_windows_byte_streams_do_not_require_fileno(monkeypatch):
    import sys
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(setmode=lambda *_args: pytest.fail("no real pipe")))
    monkeypatch.setattr(native_host, "os", SimpleNamespace(name="nt", O_BINARY=32768))
    monkeypatch.setattr(native_host, "dispatch", lambda *_args: {"ok": True})
    output = io.BytesIO()
    assert native_host.serve(ORIGIN, stdin=io.BytesIO(frame({"op": "status"})), stdout=output) == 0


@pytest.fixture
def keychain_install(installed, keychain_store, monkeypatch):
    from types import SimpleNamespace
    from aside_jev import credentials
    monkeypatch.setattr(credentials, 'sys', SimpleNamespace(platform='darwin'))
    return installed, keychain_store


def test_native_key_save_replace_is_scoped_and_never_returns_secret(keychain_install):
    profile, store = keychain_install
    root = control.config_root()
    original = control._load_config(root)
    for secret in ('fixture-first-private', 'fixture-second-private'):
        result = invoke({'op': 'set_api_key', 'secret': secret})
        assert result['ok'] is True
        assert result['status']['key_status'] == 'configured'
        assert result['status']['enabled'] is False
        config = control._load_config(root)
        assert config['profile_dir'] == original['profile_dir']
        assert config['env_file'] is None
        assert store.values == {config['keychain_account']: secret}
        assert secret not in json.dumps(result)
        assert all(secret.encode() not in p.read_bytes() for p in root.rglob('*') if p.is_file())
    assert not (profile / 'AGENTS.md').exists()
    assert not (root / 'api.env').exists()


@pytest.mark.parametrize('message', [
    {'op': 'set_api_key', 'secret': ''},
    {'op': 'set_api_key', 'secret': 'with space'},
    {'op': 'set_api_key', 'secret': 'x' * 4097},
    {'op': 'set_api_key', 'secret': 123},
    {'op': 'set_api_key', 'secret': 'fixture', 'root': '/tmp/other'},
    {'op': 'set_api_key', 'secret': 'fixture', 'account': 'other'},
])
def test_native_key_rejects_invalid_input_before_keychain_write(keychain_install, message):
    _, store = keychain_install
    assert invoke(message)['ok'] is False
    assert not store.calls


def test_native_key_wrong_origin_cannot_write(keychain_install):
    _, store = keychain_install
    result = invoke({'op': 'set_api_key', 'secret': 'fixture'}, origin='chrome-extension://' + 'b' * 32 + '/')
    assert result['error']['code'] == 'origin'
    assert not store.calls


def test_native_key_denial_does_not_create_plaintext_fallback(keychain_install, monkeypatch):
    _, store = keychain_install
    def denied(*args, **kwargs):
        raise control.ControlError('keychain_access', 'Keychain denied.')
    monkeypatch.setattr(store, 'get', denied)
    previous = (control.config_root() / 'config.json').read_bytes()
    result = invoke({'op': 'set_api_key', 'secret': 'fixture-private'})
    assert result['error']['code'] == 'keychain_access'
    assert not store.values
    assert (control.config_root() / 'config.json').read_bytes() == previous
    assert not (control.config_root() / 'api.env').exists()


def test_native_key_unsupported_platform_does_not_write(installed, monkeypatch, keychain_store):
    from types import SimpleNamespace
    from aside_jev import credentials
    monkeypatch.setattr(credentials, 'sys', SimpleNamespace(platform='win32'))
    result = invoke({'op': 'set_api_key', 'secret': 'fixture'})
    assert result['error']['code'] == 'keychain_platform'
    assert not keychain_store.calls


def test_manual_connection_probe_and_status_persistence(installed, monkeypatch):
    from aside_jev import connection_check
    assert invoke({'op': 'status'})['status']['connection_check']['state'] == 'unverified'
    result = invoke({'op': 'check_connection'})
    assert result['ok'] is True
    checked = result['status']['connection_check']
    assert checked['state'] == 'ready'
    assert checked['scope'] == 'local_mcp_probe'
    assert checked['tool_count'] >= 4
    assert result['status']['mcp_connected'] is None
    monkeypatch.setattr(connection_check, 'run', lambda *_: pytest.fail('status must not start probe'))
    assert invoke({'op': 'status'})['status']['connection_check'] == checked


def test_manual_probe_rejects_origin_fields_and_duplicate_requests(installed, monkeypatch):
    from aside_jev import connection_check
    monkeypatch.setattr(connection_check, 'run', lambda *_: pytest.fail('must not start'))
    assert invoke({'op': 'check_connection'}, origin='chrome-extension://' + 'b' * 32 + '/')['error']['code'] == 'origin'
    assert invoke({'op': 'check_connection', 'command': 'bad'})['error']['code'] == 'input'
    with control._lock(control.config_root()):
        assert invoke({'op': 'check_connection'})['error']['code'] == 'busy'
