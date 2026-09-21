"""Credential fakes are opt-in; native tests use an isolated real keychain."""
import pytest

from aside_jev import keychain


class MemoryKeychain:
    def __init__(self):
        self.values = {}
        self.calls = []

    def get(self, account, *, allow_interaction=False):
        self.calls.append(("get", account))
        return self.values.get(account)

    def contains(self, account):
        self.calls.append(("contains", account))
        return account in self.values

    def set(self, account, secret):
        self.calls.append(("set", account))
        self.values[account] = secret

    def delete(self, account):
        self.calls.append(("delete", account))
        return self.values.pop(account, None) is not None


@pytest.fixture
def keychain_store(monkeypatch):
    store = MemoryKeychain()
    monkeypatch.setattr(keychain, "get_store", lambda: store)
    return store
