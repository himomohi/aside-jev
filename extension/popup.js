import { ExtensionController, nativeTransport } from "./controller.mjs";
import { createExtensionI18n } from "./region-locale.mjs";
import { errorText, warningText } from "./errors.mjs";
const i18n = createExtensionI18n();
const t = (key, values) => i18n.t(key, values);

const $ = (id) => document.getElementById(id);
const runtime = globalThis.chrome?.runtime;
const controller = new ExtensionController(nativeTransport(runtime, 60000), render);

function render({ status, busy, operation, error, errorCode }) {
  const fullyReady = status?.execution_ready ?? status?.enabled;
  document.body.setAttribute("aria-busy", String(busy));
  document.body.setAttribute("data-ready", String(!!fullyReady && !busy));
  $("warning-dot").hidden = !status?.warnings?.length;
  if (error || status?.activation?.state === "failed" || status?.connection_check?.state === "failed") {
    $("diagnostics").hidden = false;
    $("info-button").setAttribute("aria-expanded", "true");
  }
  $("error").hidden = !error;
  $("error").textContent = error ? errorText(errorCode, error, t) : "";
  $("warnings").hidden = !status?.warnings?.length;
  $("warnings").textContent = warningText(status, t);
  $("setup").hidden = !!status || busy;
  $("connected").hidden = !status;
  $("open-keychain").hidden = !status?.keychain_ui_supported;
  $("open-keychain").disabled = busy;
  const keyAction = t(status?.live_available ? "Replace API key" : "Set up API key");
  $("open-keychain").setAttribute("aria-label", keyAction);
  $("open-keychain").title = keyAction;
  $("toggle").disabled =
    busy || !status || (!status.enabled && !status.live_available);
  $("toggle").setAttribute("aria-checked", String(!!fullyReady));
  $("toggle").title = t(fullyReady ? "Turn off" : "Verify and connect");
  $("toggle").setAttribute("aria-label", $("toggle").title);
  for (const id of ["save", "refresh", "reconnect", "check-connection", "copy-mcp"]) $(id).disabled = busy;
  if (busy && operation === "check_connection") {
    $("probe-status").textContent = t("Checking…");
    $("probe-recovery").hidden = true;
  }
  if (busy) {
    $("state-label").textContent = t("Checking…");
    $("state-detail").textContent = t("Please wait");
    return;
  }
  if (!status) {
    $("state-label").textContent = t("Setup required");
    $("state-detail").textContent = t("Connection unverified");
    $("mode-description").textContent =
      t("Connect the local helper to get started.");
    $("state-dot").className = "dot";
    $("footer-status").textContent = t("ON/OFF status unverified");
    return;
  }
  $("state-label").textContent = fullyReady
    ? t("Connected")
    : t(status.enabled ? "Check connection" : "Off");
  $("state-detail").textContent = t(fullyReady ? "For new Aside tasks" : "Checks required before execution");
  $("state-dot").className = fullyReady ? "dot on" : "dot";
  $("mode-description").textContent = status.enabled
    ? t("Tasks are instructed to ask Jev to choose actions.")
    : t("Turn on to apply Jev instructions to browser tasks.");
  $("profile").textContent = status.profile_label || t("Profile selected during setup");
  $("key-status").textContent = status.live_available
    ? t(fullyReady ? "Authentication verified" : "Configured · auth unverified")
    : t("API key required");
  $("model").textContent = status.model || "jev-latest";
  $("confidence").value = status.min_confidence;
  $("timeout").value = status.timeout_s;
  $("mcp-status").textContent = status.mcp_registration === "configured"
    ? t("Registered")
    : t("Connect in Aside settings");
  $("activation-status").textContent = t(fullyReady ? "All connection checks passed" : status.activation?.stage === "api" ? "Check API key and model access, then retry ON." : status.activation?.stage === "mcp" ? "Local MCP failed. Check the helper installation, then retry ON." : status.activation?.stage === "aside" ? "Open Aside MCP settings, reconnect Jev, then retry ON." : "Press ON to verify MCP, API and Aside before execution.");
  const check = status.connection_check;
  const local = check?.scope === "local_mcp_probe";
  const probeState = local ? check.state : "unverified";
  $("probe-status").textContent = t({
    ready: "Ready · local only", failed: "Check failed", checking: "Checking…",
  }[probeState] || "Not checked");
  // 로컬 진단 결과로 실제 Aside 세션의 도구 연결을 추정하지 않는다.
  $("session-status").textContent = t("Unverified");
  $("probe-recovery").hidden = probeState !== "failed";
  $("probe-detail").textContent = local && check.checked_at
    ? t("Last local check: {time} · tools: {count}", {
      time: check.checked_at, count: Number.isInteger(check.tool_count) ? check.tool_count : 0,
    }) : "";
  $("footer-status").textContent = t("Local helper connected");
  $("scope-note").textContent = status.enabled
    ? t("Use Jev MCP in a new task. Running tasks are not switched automatically.")
    : t("While OFF, this extension’s Jev MCP rejects new decisions. Enable it before starting a new task.");
}

for (const [button, panel] of [["info-button", "diagnostics"], ["settings-button", "settings"]]) {
  $(button).addEventListener("click", () => {
    const opening = $(panel).hidden;
    for (const [otherButton, otherPanel] of [["info-button", "diagnostics"], ["settings-button", "settings"]]) {
      $(otherPanel).hidden = true;
      $(otherButton).setAttribute("aria-expanded", "false");
    }
    $(panel).hidden = !opening;
    $(panel).open = opening;
    $(button).setAttribute("aria-expanded", String(opening));
  });
}
function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
}
$("toggle").addEventListener("click", () => controller.toggle());
$("refresh").addEventListener("click", () => controller.refresh());
$("check-connection").addEventListener("click", () => controller.checkConnection());
$("reconnect").addEventListener("click", () => controller.refresh());
$("open-keychain").addEventListener("click", async () => {
  try {
    await chrome.windows.create({
      url: runtime.getURL("keychain.html"), type: "popup", width: 460, height: 580,
    });
  } catch {
    toast(t("Could not open the key window. Please try again."));
  }
});
$("extension-id").textContent = runtime?.id || t("Available after installing the extension");
$("copy-id").disabled = !runtime?.id;
$("copy-id").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(runtime.id);
    toast(t("Extension ID copied."));
  } catch {
    toast(t("Select and copy the extension ID above."));
  }
});
$("copy-mcp").addEventListener("click", async () => {
  const config = controller.state.status?.mcp_config;
  if (!config) {
    toast(t("See the setup guide for MCP connection settings."));
    return;
  }
  try {
    await navigator.clipboard.writeText(JSON.stringify(config, null, 2));
    toast(t("MCP settings copied. Add the connection in Aside settings."));
  } catch {
    toast(t("See the setup guide for MCP settings."));
  }
});
$("settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!i18n.validate($("settings-form"))) return;
  if (
    await controller.configure(
      Number($("confidence").value),
      Number($("timeout").value),
    )
  )
    toast(t("Decision settings saved."));
});
$("language-select").value = i18n.selection;
$("language-select").addEventListener("change", async () => {
  const drafts = [$("confidence").value, $("timeout").value];
  i18n.setLanguage($("language-select").value);
  await i18n.resolve();
  globalThis.chrome?.action?.setTitle({ title: t("Aside Jev · Decision instructions") });
  i18n.apply();
  render(controller.state);
  [$("confidence").value, $("timeout").value] = drafts;
  $("extension-id").textContent = runtime?.id || t("Available after installing the extension");
  $("toast").hidden = true;
  document.querySelectorAll("input").forEach((field) => field.setCustomValidity(""));
});
i18n.apply();
controller.refresh();

// 자동 감지는 사용자가 입력한 설정 초안을 덮어쓰지 않는다.
i18n.resolve().then(() => {
  const drafts = [$("confidence").value, $("timeout").value];
  i18n.apply();
  render(controller.state);
  [$("confidence").value, $("timeout").value] = drafts;
  globalThis.chrome?.action?.setTitle({ title: t("Aside Jev · Decision instructions") });
});
