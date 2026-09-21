**English** | [한국어](EXTENSION.ko.md)

# Install Aside Jev

## Quick installation

1. Install [Aside](https://aside.com/download), sign in, and launch it once. Then quit Aside before applying setup.
2. [Download this project's ZIP](https://github.com/himomohi/aside-jev/archive/refs/heads/main.zip), extract it, and run **Install.command** (macOS) or **Install.cmd** (Windows).
3. Choose your account, enter your Jev API key in the hidden prompt, and confirm the displayed paths. Reopen Aside → Extensions → Developer mode → **Load unpacked** → select the extension folder printed by setup. Pin Aside Jev, turn **ON**, and start a new task.

No Git, Python, or uv installation is required beforehand. The launcher downloads uv 0.12.17 if needed, verifies its archive SHA-256, prepares Python 3.11, installs dependencies from the checked-in `uv.lock` with hash verification, and installs the package into its own environment. Internet access is needed for these downloads. It does not change PATH, execution policy, login items, or OS services. The Native Messaging helper runs only when the popup requests it; Aside manages the MCP process.

The installer copies the packaged extension to a stable directory, so deleting the extracted ZIP folder afterwards will not break the connection. It merges only `mcp.servers.aside-jev` in the selected account's `settings.json`. Other settings and MCP entries are retained; changed files are backed up. An unrelated existing `aside-jev` entry is rejected. **Keep Aside closed while applying**, because a running app may save its own cached settings later.

The extension has a fixed public key and ID: `pendehmejnpgceflngbnbpagpodiiemg`. The public key is not a secret; no private signing key is shipped. You do not need to copy an extension ID for a fresh guided install.

### English / Korean

English is the default. From the extracted folder:

| Platform | Korean setup |
| --- | --- |
| macOS Terminal | `bash scripts/install.sh --lang ko` |
| Windows Command Prompt | `.\Install.cmd --lang ko` |

If macOS cannot open the downloaded `.command`, use `bash scripts/install.sh` in Terminal. OS security policies remain in effect. On managed Windows devices, download or execution restrictions must be handled through your normal administrator process.

<a id="windows"></a>

## Windows registration

Aside officially announced Windows availability in [v1.0.914.1](https://docs.aside.com/changelog/native). Native Messaging uses a [browser-specific Windows registry key](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging), whereas macOS uses a manifest directory.

Setup proposes `Software\Aside\NativeMessagingHosts\com.aside_jev.control` **only if the Aside NativeMessagingHosts parent already exists** in HKCU or HKLM. A product/update registry key alone is not enough. If no parent is found, supply the Native Messaging key verified for your installed Aside build with `--windows-registry-key`, or at the prompt. The installer does not guess or register Chrome/Edge as a fallback. If you cannot confirm the key, stop there; Python package installation alone does not establish browser integration.

Registration writes only the specified host under **HKCU**, without administrator elevation. The installer detects conflicting registrations and backs up files; registration failure rolls back the file changes. Windows wrappers support native binary framing and browser `--parent-window` arguments. File access inherits the parent directory's Windows ACL.

**Verification boundary:** [Windows and macOS CI passed](https://github.com/himomohi/aside-jev/actions/runs/35501878103), including actual launchers, installation, Korean setup output, settings preservation, and native message framing. Windows also registered and removed an isolated test HKCU host. These checks use synthetic accounts; an actual Aside extension-to-host connection and its Windows registry lookup key remain unverified. See [validation](VALIDATION.md).

## Locations

| Item | macOS | Windows |
| --- | --- | --- |
| Python environment and installer files | `~/Library/Application Support/AsideJev` | `%LOCALAPPDATA%\AsideJev` |
| Configuration, extension, backups | `~/.config/aside-jev` | `%USERPROFILE%\.config\aside-jev` |
| API key | User's default macOS Keychain | `api.env` in the configuration directory, or the supplied env file |
| Account detection | Existing `~/.aside/u/<number>/settings.json` | Existing `%USERPROFILE%\.aside\u\<number>\settings.json` |
| Native host registration | Existing Aside data directory → `NativeMessagingHosts` | Explicit HKCU host key → manifest in configuration directory |

Custom account paths are accepted when auto-detection finds no account. `ASIDE_JEV_INSTALL_DIR` overrides the runtime location; `--config-dir` or `ASIDE_JEV_CONFIG_DIR` overrides configuration. Use real local paths; symbolic links, Windows junctions, network paths and device paths are not supported for connection files. On Windows, the configuration folder must not contain `%`, because Windows expands it before launching a `.cmd` native host; choose another folder with `--config-dir`.

## API key and settings

Setup accepts a hidden terminal key, an existing key file through `--env-file`, or a `TYPESAFE_API_KEY` / `TYPESAFEAI_API_KEY` environment value. **macOS guided setup saves the key in Keychain**, keeping only a profile-scoped reference in configuration. It verifies the saved value and never falls back to plaintext if Keychain access fails. `--env-file` is an import source on macOS; external source files are not deleted. See [Keychain migration, rotation, and deletion](KEYCHAIN.md).

Windows retains **unencrypted local environment-file storage**. A fresh terminal-only key is saved after confirmation so browser launches can use it later. Files accept simple assignments of the two key names and are never executed as shell scripts. On either platform, saved keys are never printed or returned to the popup.

On macOS, use the popup’s key icon if you skipped key entry; on Windows, rerun setup. ON stays unavailable until a key is configured and readable. Key presence does not verify API authentication. The popup distinguishes saved MCP configuration from a verified running MCP connection.

### Connection checks

ON, MCP registration, the manual local probe, and tools available in an Aside session are separate states. The ↻ icon runs a bounded initialize/tools/list check without an API request; it does not certify the current session. If Aside shows `0 tools cached`, open **Settings → Plugins & MCPs → MCPs → aside-jev actions → Refresh tools**, then start a new task and call `jev_extension_status`. The installed skill uses that MCP status tool instead of launching a developer venv inside the task sandbox. Native built-in tools are not globally intercepted.

## Preview and advanced setup

For developers with uv already installed:

```bash
uv run aside-jev setup --dry-run
uv run aside-jev setup --lang ko
```

`setup --dry-run` never writes connection files, registry entries, or Keychain items. The outer Install launcher still prepares the package environment before invoking it. Use `setup --help` for `--profile-dir`, `--native-host-dir`, `--windows-registry-key`, `--env-file`, `--config-dir`, and `--yes` (explicit noninteractive application, no key prompt).

The original `scripts/setup_extension.py` remains available for manual extension IDs and explicit paths. Its default is preview; `--apply` registers only the local helper and does not automatically merge MCP settings. This legacy low-level helper retains environment-file compatibility; use guided `setup` or `keychain migrate` for macOS Keychain storage.

## Update, disable, and remove

- **Update a guided installation:** download the new ZIP and run the same launcher with the same install/config directories. On macOS this migrates the configured legacy key to Keychain and removes only the unchanged installer-managed `api.env` after verification. External files and historical backups are retained. Reload the extension and restart its MCP connection after updating.
- **Earlier manual installation:** the new fixed extension ID or key-file path may differ. Setup refuses to replace an existing connection with another identity. Turn the old popup OFF, disable its MCP entry, remove the old extension, and archive the old preview-listed host registration and config before starting a fresh guided install. Keep backups until the new setup works.
- **Disable:** turn OFF and start a new task. It removes only the selected account's managed instructions; new decisions in the dedicated MCP stop. In-flight actions are not undone.
- **Remove:** turn OFF, disable/remove the Jev MCP entry in Aside, and remove the extension. On macOS run `aside-jev keychain delete` with the configured installation **before removing its config**, to delete its exact Keychain item. Archive the installer/config directories and the exact preview-listed host manifest. On Windows remove only the displayed `HKCU\…\com.aside_jev.control` host key owned by this installation; do not remove parent registry keys. Restore account documents from backups if needed.

ON applies to new task instructions and the dedicated Jev MCP path. It does not intercept every built-in Aside tool. The extension requests only `nativeMessaging`, with no all-sites permission, content script, or background service worker.

## ON readiness gate

ON now runs a bounded local MCP handshake/tool inventory check, a live Jev API check using synthetic data, and an actual Aside REPL check of the registered server, cached required tools and browser RPC. Only a successful activation grants `execution_ready=true`; all extension decision tools enforce this flag. `enabled` remains the instruction state, not permission to execute. The popup switch displays execution readiness. Failures identify MCP/API/Aside recovery steps. Saving credentials, changing configuration, switching OFF or one hour of elapsed time invalidates readiness. Re-run ON after recovery. Existing native Aside tools are not globally intercepted, and existing sessions may still need reconnection. ON verification makes one small live API request; no personal browser content is sent.
