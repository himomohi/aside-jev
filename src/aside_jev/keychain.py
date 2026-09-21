"""macOS generic passwords via Security.framework; never pass secrets to a shell.

The unsigned Python CLI uses the user's file-based default keychain. Explicit
keychain paths are supported for isolated integration tests, not read from env.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes as C
from functools import lru_cache
import hashlib
import os
from pathlib import Path
import sys
import threading
from typing import Iterator

from .native_platform import ControlError

SERVICE = "com.aside_jev.api-key"
NOT_FOUND = -25300
DUPLICATE = -25299
MAX_KEY_BYTES = 4096
_INTERACTION_LOCK = threading.RLock()


def account_id(root: Path, profile: Path) -> str:
    """Bind the reference to one installation/profile without exposing its name."""
    parts = [os.path.abspath(os.fspath(path)) for path in (root, profile)]
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def validate_secret(secret: str) -> str:
    if (not isinstance(secret, str) or not secret or len(secret) > MAX_KEY_BYTES
            or not secret.isascii() or any(not 33 <= ord(char) <= 126 for char in secret)):
        raise ControlError("key_format", "API key must contain 1..4096 printable non-space ASCII characters.")
    return secret


def _check(status: int) -> None:
    if status == 0:
        return
    if status in (-128, -25293, -25308):
        raise ControlError("keychain_access", "Keychain access was denied or requires unlocking. Unlock your keychain and rerun setup; no plaintext fallback is used.")
    raise ControlError("keychain_unavailable", f"macOS Keychain operation failed (OSStatus {status}). No plaintext fallback is used.")


class _API:
    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise ControlError("keychain_platform", "macOS Keychain is only available on macOS.")
        try:
            self.cf = C.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
            self.sec = C.CDLL("/System/Library/Frameworks/Security.framework/Security")
            p = C.c_void_p
            self._bind(self.cf, "CFRelease", [p], None)
            self._bind(self.cf, "CFStringCreateWithBytes", [p, p, C.c_long, C.c_uint32, C.c_bool], p)
            self._bind(self.cf, "CFDataCreate", [p, p, C.c_long], p)
            self._bind(self.cf, "CFDataGetLength", [p], C.c_long)
            self._bind(self.cf, "CFDataGetBytePtr", [p], p)
            self._bind(self.cf, "CFDataGetTypeID", [], C.c_ulong)
            self._bind(self.cf, "CFGetTypeID", [p], C.c_ulong)
            self._bind(self.cf, "CFDictionaryCreateMutable", [p, C.c_long, p, p], p)
            self._bind(self.cf, "CFDictionarySetValue", [p, p, p], None)
            self._bind(self.cf, "CFArrayCreate", [p, p, C.c_long, p], p)
            self._bind(self.sec, "SecKeychainGetUserInteractionAllowed", [C.POINTER(C.c_ubyte)], C.c_int32)
            self._bind(self.sec, "SecKeychainSetUserInteractionAllowed", [C.c_ubyte], C.c_int32)
            self._bind(self.sec, "SecKeychainCopyDefault", [C.POINTER(p)], C.c_int32)
            self._bind(self.sec, "SecKeychainOpen", [C.c_char_p, C.POINTER(p)], C.c_int32)
            self._bind(self.sec, "SecItemCopyMatching", [p, C.POINTER(p)], C.c_int32)
            self._bind(self.sec, "SecItemAdd", [p, C.POINTER(p)], C.c_int32)
            self._bind(self.sec, "SecItemUpdate", [p, p], C.c_int32)
            self._bind(self.sec, "SecItemDelete", [p], C.c_int32)
        except (OSError, AttributeError, ValueError):
            raise ControlError("keychain_unavailable", "macOS Keychain services could not be loaded. No plaintext fallback is used.") from None

    @staticmethod
    def _bind(library, name, args, result) -> None:
        function = getattr(library, name)
        function.argtypes = args
        function.restype = result

    def constant(self, name: str) -> C.c_void_p:
        library = self.cf if name.startswith("kCF") else self.sec
        return C.c_void_p.in_dll(library, name)

    def callbacks(self, name: str) -> C.c_void_p:
        # Callback symbols are structs, not CFTypeRef pointer variables.
        return C.c_void_p(C.addressof(C.c_byte.in_dll(self.cf, name)))

    @contextmanager
    def interaction(self, allowed: bool) -> Iterator[None]:
        # SecItem's UI flag alone is insufficient for the file-based shim.
        # Serialize our native operations while changing this process-wide flag,
        # and restore the prior policy even when a query fails. Never unlock or
        # relax a keychain's access controls here.
        with _INTERACTION_LOCK:
            previous = C.c_ubyte()
            _check(self.sec.SecKeychainGetUserInteractionAllowed(C.byref(previous)))
            if not allowed:
                _check(self.sec.SecKeychainSetUserInteractionAllowed(False))
            try:
                yield
            finally:
                if not allowed:
                    _check(self.sec.SecKeychainSetUserInteractionAllowed(previous.value))

    @contextmanager
    def dictionary(self, values: dict[str, object]) -> Iterator[int]:
        result = self.cf.CFDictionaryCreateMutable(None, 0, self.callbacks("kCFTypeDictionaryKeyCallBacks"), self.callbacks("kCFTypeDictionaryValueCallBacks"))
        if not result:
            raise ControlError("keychain_unavailable", "Could not allocate a Keychain query.")
        try:
            for name, value in values.items():
                owned = None
                if isinstance(value, str):
                    raw = value.encode("utf-8")
                    owned = self.cf.CFStringCreateWithBytes(None, raw, len(raw), 0x08000100, False)
                    ref = owned
                elif isinstance(value, bytes):
                    owned = self.cf.CFDataCreate(None, value, len(value))
                    ref = owned
                elif isinstance(value, bool):
                    ref = self.constant("kCFBooleanTrue" if value else "kCFBooleanFalse")
                else:
                    ref = value
                if not ref:
                    raise ControlError("keychain_unavailable", "Could not allocate a Keychain value.")
                try:
                    self.cf.CFDictionarySetValue(result, self.constant(name), ref)
                finally:
                    if owned:
                        self.cf.CFRelease(owned)
            yield result
        finally:
            self.cf.CFRelease(result)


@lru_cache(maxsize=1)
def _api() -> _API:
    # Cache the framework bindings, never passwords or user-specific state.
    return _API()


class KeychainStore:
    def __init__(self, *, keychain_path: Path | None = None) -> None:
        self.keychain_path = keychain_path

    @contextmanager
    def _scope(self, *, allow_interaction: bool = True) -> Iterator[tuple[_API, C.c_void_p, C.c_void_p]]:
        api = _api()
        with api.interaction(allow_interaction):
            keychain = C.c_void_p()
            status = (api.sec.SecKeychainOpen(os.fsencode(self.keychain_path), C.byref(keychain))
                      if self.keychain_path is not None else api.sec.SecKeychainCopyDefault(C.byref(keychain)))
            _check(status)
            search = None
            try:
                handles = (C.c_void_p * 1)(keychain.value)
                search = api.cf.CFArrayCreate(None, handles, 1, api.callbacks("kCFTypeArrayCallBacks"))
                if not search:
                    raise ControlError("keychain_unavailable", "Could not scope the Keychain query.")
                yield api, keychain, C.c_void_p(search)
            finally:
                if search:
                    api.cf.CFRelease(search)
                if keychain:
                    api.cf.CFRelease(keychain)

    @staticmethod
    def _identity(api: _API, account: str) -> dict[str, object]:
        if not isinstance(account, str) or len(account) != 64 or any(char not in "0123456789abcdef" for char in account):
            raise ControlError("keychain_account", "Invalid Keychain account reference.")
        return {"kSecClass": api.constant("kSecClassGenericPassword"), "kSecAttrService": SERVICE,
                "kSecAttrAccount": account, "kSecAttrSynchronizable": False,
                "kSecUseDataProtectionKeychain": False}

    def _read(self, account: str, *, metadata: bool, allow_interaction: bool) -> str | bool | None:
        with self._scope(allow_interaction=allow_interaction) as (api, _keychain, search):
            values = {**self._identity(api, account), "kSecMatchSearchList": search,
                      "kSecMatchLimit": api.constant("kSecMatchLimitOne"),
                      "kSecReturnAttributes" if metadata else "kSecReturnData": True}
            if not allow_interaction:
                values["kSecUseAuthenticationUI"] = api.constant("kSecUseAuthenticationUIFail")
            result = C.c_void_p()
            with api.dictionary(values) as query:
                status = api.sec.SecItemCopyMatching(query, C.byref(result))
            try:
                if status == NOT_FOUND:
                    return False if metadata else None
                _check(status)
                if not result:
                    raise ControlError("keychain_data", "Keychain returned an empty result.")
                if metadata:
                    return True
                if api.cf.CFGetTypeID(result) != api.cf.CFDataGetTypeID():
                    raise ControlError("keychain_data", "Keychain returned an invalid password type.")
                size = api.cf.CFDataGetLength(result)
                if not 1 <= size <= MAX_KEY_BYTES:
                    raise ControlError("keychain_data", "The stored Keychain password has an invalid size.")
                try:
                    return validate_secret(C.string_at(api.cf.CFDataGetBytePtr(result), size).decode("utf-8"))
                except (UnicodeError, ControlError):
                    raise ControlError("keychain_data", "The stored Keychain password has an invalid format.") from None
            finally:
                if result:
                    api.cf.CFRelease(result)

    def contains(self, account: str) -> bool:
        """Metadata only: never requests password bytes or interactive UI."""
        return bool(self._read(account, metadata=True, allow_interaction=False))

    def get(self, account: str, *, allow_interaction: bool = False) -> str | None:
        value = self._read(account, metadata=False, allow_interaction=allow_interaction)
        return value if isinstance(value, str) else None

    def set(self, account: str, secret: str) -> None:
        raw = validate_secret(secret).encode("utf-8")
        with self._scope() as (api, keychain, search):
            identity = self._identity(api, account)
            with api.dictionary({**identity, "kSecMatchSearchList": search}) as query, api.dictionary({"kSecValueData": raw}) as data:
                status = api.sec.SecItemUpdate(query, data)
                if status == NOT_FOUND:
                    with api.dictionary({**identity, "kSecUseKeychain": keychain, "kSecValueData": raw,
                                         "kSecAttrLabel": "Aside Jev API key"}) as item:
                        status = api.sec.SecItemAdd(item, None)
                    if status == DUPLICATE:
                        status = api.sec.SecItemUpdate(query, data)
                _check(status)

    def delete(self, account: str) -> bool:
        with self._scope() as (api, _keychain, search):
            with api.dictionary({**self._identity(api, account), "kSecMatchSearchList": search}) as query:
                status = api.sec.SecItemDelete(query)
            if status == NOT_FOUND:
                return False
            _check(status)
            return True


def get_store() -> KeychainStore:
    return KeychainStore()


def replace_verified(account: str, secret: str) -> None:
    """Read back before accepting a write; restore the old item on failure."""
    validate_secret(secret)
    store = get_store()
    old = store.get(account, allow_interaction=True)
    if old == secret:
        return
    try:
        store.set(account, secret)
        if store.get(account, allow_interaction=True) != secret:
            raise ControlError("keychain_verify", "Keychain read-back did not match. The credential change was not accepted.")
    except Exception:
        try:
            if old is None:
                store.delete(account)
            else:
                store.set(account, old)
        except Exception:
            raise ControlError("keychain_rollback", "The Keychain change could not be rolled back. Check the Aside Jev item in Keychain Access before retrying.") from None
        raise
