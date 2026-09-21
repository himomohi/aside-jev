"""Real Security.framework contract, in a disposable keychain, with fake keys."""
import hashlib
import subprocess
import sys

import pytest

from aside_jev.keychain import KeychainStore, account_id
from aside_jev.native_platform import ControlError

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="Requires real macOS Security.framework")


def security(*args):
    return subprocess.run(["/usr/bin/security", *map(str, args)], capture_output=True, check=True, timeout=15)


def test_real_isolated_keychain_roundtrip_cross_process_lock_and_delete(tmp_path):
    path = tmp_path.resolve() / "테스트 keychain.keychain-db"
    # This is only a disposable test-keychain password, never a Jev API key.
    password = "aside-jev-disposable-test-keychain"
    original_default = security("default-keychain", "-d", "user").stdout
    security("create-keychain", "-p", password, path)
    try:
        security("unlock-keychain", "-p", password, path)
        security("set-keychain-settings", "-lut", "300", path)
        store = KeychainStore(keychain_path=path)
        account = account_id(tmp_path.resolve(), tmp_path.resolve() / "profile")
        other = account_id(tmp_path.resolve(), tmp_path.resolve() / "other")
        assert not store.contains(account) and store.get(account) is None
        secret = 'fixture-"quote"-$-\\-NOT-A-REAL-API-KEY'
        store.set(account, secret)
        assert store.contains(account) and store.get(account) == secret
        assert store.get(other) is None
        script = (
            "import hashlib,sys; from pathlib import Path; from aside_jev.keychain import KeychainStore; "
            "value=KeychainStore(keychain_path=Path(sys.argv[1])).get(sys.argv[2]); "
            "assert value and hashlib.sha256(value.encode()).hexdigest()==sys.argv[3]"
        )
        subprocess.run([sys.executable, "-c", script, str(path), account, hashlib.sha256(secret.encode()).hexdigest()],
                       capture_output=True, check=True, timeout=15)
        store.set(account, "rotated-fixture-key")
        assert store.get(account) == "rotated-fixture-key"
        security("lock-keychain", path)
        with pytest.raises(ControlError) as error:
            store.get(account)  # Non-interactive: fail instead of waiting for a prompt.
        assert error.value.code.startswith("keychain_")
        security("unlock-keychain", "-p", password, path)
        assert store.delete(account) is True
        assert store.delete(account) is False
        assert not store.contains(account) and store.get(account) is None
        assert security("default-keychain", "-d", "user").stdout == original_default
    finally:
        security("delete-keychain", path)
