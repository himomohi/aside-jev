**English** | [한국어](FEATURE_MAP.ko.md)

# Feature map

| Feature | Entry point | Core files | Dependencies | Verification |
| --- | --- | --- | --- | --- |
| Toolbar ON/OFF | MV3 popup | extension/popup.js, controller.mjs | Native Messaging | tests/test_extension_controller.mjs |
| Account state and settings | native-host, extension-status | extension_control.py, native_host.py | Explicit accountRoot, key file, local config | test_extension_control.py, test_native_host.py |
| Guided install | Install.command, Install.cmd, setup CLI | installer.py, scripts/install.sh | Pinned uv/Python, packaged extension, existing Aside account | test_installer.py, macOS bootstrap |
| Native registration | setup CLI, scripts/setup_extension.py | extension_control.py, native_platform.py, native_registry.py | macOS manifest / explicit Windows HKCU key | test_extension_control.py, test_native_platform.py |
| Browser loop | jev_browser_run MCP | browser_flow.py, browser_runtime.py | Aside REPL, Jev | test_browser_flow.py, verify_browser_runtime.py |
| Confidence and OFF gates | jev_choose, jev_step, jev_system_one | mcp_server.py, extension_gate.py | Extension policy, typed responses | test_mcp_server.py, test_jev.py |
| Connection reuse | choose_live, system_one | jev.py | TypeSafe SDK, httpx2 | test_jev.py, benchmark_latency.py |
| Candidate/context bounds | parse_candidates, sanitize_context | core.py, aside_bridge.py | App candidates, page observations | test_core.py, test_observation.py |
| Local decision workspace | dashboard CLI | dashboard.py, static/ | 127.0.0.1 HTTP, session records | test_dashboard.py, Computer Use |
| Configuration diagnostics | doctor CLI | cli.py | Key presence, Aside CLI | test_cli.py |
| Localized speed duel | README GIF/MP4, bun run render | video/src/Root.tsx, i18n.ts, locales/, benchmark.json | Remotion 4.0.526, recorded aggregates | TypeScript, locale parity, frame/media checks |
| English/Korean UI | Dashboard and popup language selector | static/i18n.mjs, extension/i18n.mjs, extension/_locales/ | Local language preference; no added permissions | UI locale tests, Computer Use |

CLI help and doctor localization: `--lang en|ko` → `cli.py`, `cli_i18n.py` → `test_cli_i18n.py`. Machine-readable keys remain unchanged.

Extension ON applies to new Aside instructions and its dedicated MCP. It does not globally intercept built-in tools. See [localization](I18N.md) for English defaults and translation boundaries.
