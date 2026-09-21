[English](KEYCHAIN.md) | [한국어](KEYCHAIN.ko.md)

# macOS API key storage

On macOS, guided `setup` saves the API key in the current user's default **file-based macOS Keychain**. It does not write a new `api.env`. Windows keeps its existing environment-file behavior. No new Python dependency is required.

## Enter from the extension

Click the **key icon** beside the API key status in the popup. A separate window accepts masked input and **Save to Keychain** stores or replaces the key for the installed account. This window stays open during macOS approval. The field is cleared immediately on submission; the key is never persisted in browser storage. There is no API to retrieve or display the existing key. Input travels through Native Messaging to the local helper and Security.framework. After confirmation, close the window and reopen the popup to refresh ON availability. Saving neither authenticates with Jev nor enables it automatically.

Cancelled approval, a locked keychain, and write failures never fall back to plaintext. A timeout does not retry automatically: check for macOS approval, then refresh the status.

## Install, migrate, rotate, delete

```bash
uv run aside-jev setup
uv run aside-jev keychain status
uv run aside-jev keychain migrate
uv run aside-jev keychain set
uv run aside-jev keychain delete
```

Run these commands in the source checkout with its installed environment. `set` asks for hidden terminal input; there is deliberately no `--key` argument. `delete` asks for confirmation; `--yes` confirms it noninteractively. Add `--config-dir /absolute/path` for a different installation. Add `--lang ko` for Korean prompts.

Rerunning `setup` upgrades the selected legacy installation. `keychain migrate` upgrades an existing configuration directly, without modifying browser settings. For a new imported key, `setup --env-file /absolute/path/to/key.env` reads that file and saves the value to Keychain; it is not a persistent file reference on macOS. Conflicting key aliases are rejected rather than selecting one silently.

After an upgrade, restart Aside's extension-specific MCP connection. The installed `serve --extension` wrapper loads the current Keychain value for each policy check. General standalone `serve`, `choose`, and the demo dashboard keep their existing environment-based behavior; they are not silently assigned to an installed profile.

## What is persisted

The service name is `com.aside_jev.api-key`. The account is a SHA-256 reference derived from the installation directory and selected profile. Config JSON stores only this reference, `credential_store: "keychain"`, and `env_file: null`.

Passwords pass directly to Security.framework as in-process data, never as shell command arguments. They are not returned to the extension popup or written into new configuration backups. Runtime use still necessarily holds the key in process memory and the MCP process environment. This is Keychain storage, not a claim of Secure Enclave storage or protection from a compromised logged-in process. Synchronization is disabled.

A status check requests metadata, not password bytes. `configured` therefore means an item exists, not that the API key authenticates or that the keychain is unlocked. If runtime access is denied or locked, execution stops; it does not reuse an old environment value or fall back to plaintext. Unlock the keychain and retry. Setup and explicit key changes may require a macOS access prompt.

## Existing plaintext copies

Migration reads back the new Keychain value before changing the credential reference permanently. A failed credential write rolls back the configuration transaction and attempts to restore the prior Keychain item.

Only the old installer's unchanged `<config-dir>/api.env` is automatically removed, **after a verified migration**. External source files and historical backups are never swept or deleted automatically. The installer reports a cleanup error if that managed file changes or cannot be removed. Review remaining source files/backups and revoke or rotate previously exposed keys as appropriate. File deletion is not guaranteed secure erasure.

Deletion removes only this installation's exact service/account item; it leaves browser settings intact. Subsequent extension policy checks discard cached environment aliases and stop when the item is absent. It does not cancel an already-sent API request or revoke the key at the provider.

## Verification scope

`tests/test_keychain.py` covers default installation, migration, rollback, deletion, stale environment values, and refusal of insecure fallback with an in-memory store. Existing installer unit tests explicitly use that fixture and do not write to a user's keychain.

`tests/test_keychain_native.py` separately exercises real Security.framework on macOS with dummy credentials in a disposable keychain: save/read/update, cross-process lookup, locked-keychain failure, isolation, and deletion. It does not replace the default keychain. No test calls the live Jev API or uses a real Aside account.

[Back to setup](EXTENSION.md) · [Development checks](DEVELOPMENT.md)
