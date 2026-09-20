**English** | [한국어](EXTENSION.ko.md)

# Connect the Aside toolbar extension

The package consists of an MV3 popup, an on-demand Native Messaging helper, and a persistent MCP process. The extension requests only `nativeMessaging`: no background service worker, content script, or all-sites permission. It does not create an OS service or login item.

## Setup

1. Run `uv sync` to prepare the Python environment.
2. Load this repository's `extension/` directory as an unpacked extension in Aside's extension manager. Moving the directory can change its extension ID.
3. Identify the extension ID, target Aside `accountRoot`, and Native Messaging registration directory for your Aside build. The installer does not guess account or host paths.
4. Preview with your actual values:

```bash
uv run python scripts/setup_extension.py \
  --extension-id '32-character-ID-from-extension-manager' \
  --profile-dir '/absolute/Aside/accountRoot' \
  --native-host-dir '/absolute/Aside/NativeMessagingHosts' \
  --env-file '/absolute/path/to/key-env-file' \
  --profile-label 'My Aside account' \
  --dry-run
```

Review the target paths, then replace `--dry-run` with `--apply` to register the connection files. Existing files are backed up. Native Messaging registration adds a program-execution connection; follow the approval policy of the installation environment.

The key file permits simple assignments of `TYPESAFE_API_KEY` or `TYPESAFEAI_API_KEY` only. It is not sourced as shell code, and arbitrary commands are not executed. Raw keys are never shown in the popup or status response.

5. Use the popup's **Copy MCP config**, or `mcp_config` / `aside_mcp_entry` from `uv run aside-jev extension-status`, to register the MCP connection in Aside. The dedicated wrapper runs `serve --extension` and checks ON/OFF for each request. If installed with a custom `--config-dir`, use the same `ASIDE_JEV_CONFIG_DIR` for status checks.
6. Refresh the popup's connection and turn ON. The UI confirms key presence and saved instructions before displaying ON. Key presence does not verify API authentication.
7. Start a **new Aside task**. Route continuous browser work through `jev_browser_run`.

The popup defaults to English and offers a persistent `English / 한국어` selector. Extension-manager metadata follows the browser's locale through Chrome's `_locales` mechanism, with English as `default_locale`; it can differ from the popup selection.

## Meaning of ON/OFF

- **ON:** apply the managed AGENTS.md block and `skills/user/aside-jev/SKILL.md` in the selected accountRoot. Recheck enabled state at execution boundaries.
- **OFF:** remove that managed block, retain the status-check skill, and reject new decisions in the extension-specific MCP. Already-started network/browser actions are not undone.
- Warn when old Jev instructions remain in home/global Aside instructions. The extension does not edit global files automatically.
- If disconnected or unable to save, show that status needs checking rather than retaining a stale ON indicator.
- There is no hook intercepting every built-in tool. Enforcement is limited to the provided MCP path.

## Disable and remove

Turn OFF in the popup and use a new task. To remove completely, disable the MCP connection in Aside settings and remove the extension. The preview-listed Native Messaging manifest and wrappers in the configuration directory may be archived or removed. Restore account documents from backups if needed. Other tools' files and global AGENTS.md are outside the removal scope.

## Validation boundary

Temporary profiles cover native framing, origin checks, ON/OFF, backups, failure recovery, and generated wrapper execution. Loading the extension into a real user Aside account and registering Native Messaging there have not been verified. Confirm the registration path and UI connection in the installation environment.
