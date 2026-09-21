**English** | [한국어](FEATURE_MAP.ko.md)

# Feature map

| Feature | Entry point | Core files | Dependencies | Verification |
| --- | --- | --- | --- | --- |
| ON readiness gate | Popup ON → activate | activation.py, extension_gate.py, native_host.py | MCP / live API / Aside RPC | test_activation.py, actual popup + session |
| Manual MCP probe / recovery | Popup ↻, check_connection | connection_check.py, extension_control.py, native_host.py, popup.js | Installed launcher, initialize/tools/list; separate session verification | test_connection_check.py, test_native_host.py, test_ui_flow.mjs |
| macOS key entry / replacement | Popup key icon → separate window | extension/keychain.*, keychain-form.mjs, native_host.dispatch (set_api_key), credentials.manage | Native Messaging, Security.framework | test_native_host.py, test_keychain_native.py, test_keychain_form.mjs, Computer Use |
| Toolbar ON/OFF | MV3 popup | extension/popup.js, controller.mjs | Native Messaging | tests/test_extension_controller.mjs |
| Account state and settings | native-host, extension-status | extension_control.py, native_host.py | Explicit accountRoot, key file, local config | test_extension_control.py, test_native_host.py |
| Guided install | Install.command, Install.cmd, setup CLI | installer.py, scripts/install.sh | Pinned uv/Python, packaged extension, existing Aside account | test_installer.py, macOS bootstrap |
| Native registration | setup CLI, scripts/setup_extension.py | extension_control.py, native_platform.py, native_registry.py | macOS manifest / explicit Windows HKCU key | test_extension_control.py, test_native_platform.py |
| Browser loop | jev_browser_run MCP | browser_flow.py, browser_runtime.py, mcp_server.py | Aside REPL, Jev | test_browser_flow.py, verify_browser_runtime.py |
| Confidence and OFF gates | jev_choose, jev_step, jev_system_one | mcp_server.py, extension_gate.py | Extension policy, typed responses | test_mcp_server.py, test_jev.py |
| Connection reuse | choose_live, system_one | jev.py | TypeSafe SDK, httpx2 | test_jev.py, benchmark_latency.py |
| Candidate/context bounds | parse_candidates, sanitize_context | core.py, aside_bridge.py | App candidates, page observations | test_core.py, test_observation.py |
| Local decision workspace | dashboard CLI | dashboard.py, static/ | 127.0.0.1 HTTP, session records | test_dashboard.py, Computer Use |
| Configuration diagnostics | doctor CLI | cli.py | Key presence, Aside CLI | test_cli.py |
| Localized speed duel | README GIF/MP4, bun run render | video/src/Root.tsx, i18n.ts, locales/, benchmark.json | Remotion 4.0.526, recorded aggregates | TypeScript, locale parity, frame/media checks |
| English/Korean UI | Dashboard and popup language selector | static/i18n.mjs, extension/i18n.mjs, extension/_locales/ | Local language preference; no added permissions | UI locale tests, Computer Use |

CLI help and doctor localization: `--lang en|ko` → `cli.py`, `cli_i18n.py` → `test_cli_i18n.py`. Machine-readable keys remain unchanged.

Extension ON applies to new Aside instructions and its dedicated MCP. It does not globally intercept built-in tools. See [localization](I18N.md) for English defaults and translation boundaries.

| Extension IP language | Auto (IP) selector | extension/region-locale.mjs, popup.js, keychain.js | Country.is country lookup, browser fallback | test_ui_i18n.mjs, test_ui_flow.mjs |

| Compact icon popover | Power switch, key, probe, settings, info icons | popup.html, popup.css, popup.js | Native control, IP i18n; diagnostic panels | test_ui_flow.mjs, installed Aside CUA |
