"""Optional Rust engine, selected once at process startup before any requests."""
from __future__ import annotations

import os

ENGINE = os.environ.get("ASIDE_JEV_ENGINE", "auto").strip().lower()
if ENGINE not in ("auto", "python", "rust"):
    raise RuntimeError("ASIDE_JEV_ENGINE must be auto, python, or rust")

native = None
if ENGINE != "python":
    try:
        import _aside_jev_native as native
    except ModuleNotFoundError as error:
        if error.name != "_aside_jev_native" or ENGINE == "rust":
            raise RuntimeError("Rust core is unavailable. Install the native extra with a Rust toolchain.") from error


def normalize_refs(tree: str) -> str:
    if native is not None:
        try:
            return native.normalize_refs(tree)
        except UnicodeEncodeError:
            # JSON/JS can contain isolated surrogates; Rust strings cannot.
            pass
    # Import locally to keep browser_runtime's public REF constant compatible.
    from .browser_runtime import REF
    return REF.sub("[ref]", tree)


def http_transport():
    if native is None:
        return None
    import httpx2

    class RustTransport(httpx2.BaseTransport):
        def __init__(self):
            self.client = native.HttpClient()

        def handle_request(self, request):
            client = self.client
            if client is None:
                raise httpx2.TransportError("Rust HTTP client is closed")
            timeout = request.extensions.get("timeout", {}).get("read", 15.0)
            try:
                status, headers, content = client.request(
                    request.method, str(request.url), list(request.headers.multi_items()), request.read(), timeout,
                )
            except TimeoutError:
                raise httpx2.ReadTimeout("Rust HTTP deadline exceeded", request=request) from None
            except (RuntimeError, ValueError):
                raise httpx2.TransportError("Rust HTTP request failed", request=request) from None
            return httpx2.Response(status, headers=headers, content=content, request=request)

        def close(self):
            self.client = None

    return RustTransport()
