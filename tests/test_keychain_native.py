"""Real Security.framework contract, in a disposable keychain, with fake keys."""
import hashlib
from pathlib import Path
import subprocess
import sys

import pytest

from aside_jev.keychain import KeychainStore, account_id, _api
from aside_jev.native_platform import ControlError

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="Requires real macOS Security.framework")
PASSWORD = "aside-jev-disposable-test-keychain"


def security(*args):
    return subprocess.run(["/usr/bin/security", *map(str, args)], capture_output=True, check=True, timeout=15)


def native_contract(path):
    # CI must fail, not open a prompt. Nested operations restore this policy.
    with _api().interaction(False):
        store = KeychainStore(keychain_path=path)
        account = account_id(path.parent, path.parent / "profile")
        other = account_id(path.parent, path.parent / "other")
        print("missing", flush=True)
        assert not store.contains(account) and store.get(account) is None
        secret = 'fixture-"quote"-$-\\-NOT-A-REAL-API-KEY'
        print("write/read", flush=True)
        store.set(account, secret)
        assert store.contains(account) and store.get(account) == secret
        assert store.get(other) is None
        script = (
            "import hashlib,sys; from pathlib import Path; from aside_jev.keychain import KeychainStore; "
            "value=KeychainStore(keychain_path=Path(sys.argv[1])).get(sys.argv[2]); "
            "assert value and hashlib.sha256(value.encode()).hexdigest()==sys.argv[3]"
        )
        print("cross-process", flush=True)
        subprocess.run([sys.executable, "-c", script, str(path), account, hashlib.sha256(secret.encode()).hexdigest()],
                       capture_output=True, check=True, timeout=15)
        print("rotation", flush=True)
        store.set(account, "rotated-fixture-key")
        assert store.get(account) == "rotated-fixture-key"
        print("locked read", flush=True)
        security("lock-keychain", path)
        with pytest.raises(ControlError) as error:
            store.get(account)
        assert error.value.code.startswith("keychain_")
        security("unlock-keychain", "-p", PASSWORD, path)
        print("delete", flush=True)
        assert store.delete(account) is True
        assert store.delete(account) is False
        assert not store.contains(account) and store.get(account) is None
        print("complete", flush=True)


def test_real_isolated_keychain_roundtrip_cross_process_lock_and_delete(tmp_path):
    path = tmp_path.resolve() / "테스트 keychain.keychain-db"
    original_default = security("default-keychain", "-d", "user").stdout
    # This is only a disposable keychain password, never a Jev API key.
    security("create-keychain", "-p", PASSWORD, path)
    try:
        security("unlock-keychain", "-p", PASSWORD, path)
        security("set-keychain-settings", "-lut", "300", path)
        # Bound even an unexpected native UI deadlock, and retain phase evidence.
        try:
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(path)],
                                    capture_output=True, text=True, timeout=45)
        except subprocess.TimeoutExpired as error:
            pytest.fail(f"Native Keychain contract timed out; phases: {error.stdout!r}")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "complete" in result.stdout
        assert security("default-keychain", "-d", "user").stdout == original_default
    finally:
        security("delete-keychain", path)


if __name__ == "__main__":
    native_contract(Path(sys.argv[1]))
