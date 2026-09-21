import pytest
from aside_jev import keychain


@pytest.mark.parametrize("initial", [0, 1])
def test_native_ui_policy_restored_after_error(initial):
    import ctypes as C
    class Security:
        state = initial
        def SecKeychainGetUserInteractionAllowed(self, value):
            C.cast(value, C.POINTER(C.c_ubyte)).contents.value = self.state
            return 0
        def SecKeychainSetUserInteractionAllowed(self, value):
            self.state = int(value)
            return 0
    api = object.__new__(keychain._API)
    api.sec = Security()
    with pytest.raises(RuntimeError, match="failure"):
        with api.interaction(False):
            assert api.sec.state == 0
            with api.interaction(True):
                assert api.sec.state == 0  # An inner write cannot override no-UI.
            raise RuntimeError("failure")
    assert api.sec.state == initial
