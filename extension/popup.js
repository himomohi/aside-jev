import { ExtensionController, nativeTransport } from "./controller.mjs";
import { createI18n } from "./i18n.mjs";
import { errorText, warningText } from "./errors.mjs";
const i18n = createI18n("aside-jev.extension.language");
const t = (key, values) => i18n.t(key, values);

const $ = (id) => document.getElementById(id);
const runtime = globalThis.chrome?.runtime;
const controller = new ExtensionController(nativeTransport(runtime), render);

function render({ status, busy, error, errorCode }) {
  document.body.setAttribute("aria-busy", String(busy));
  $("error").hidden = !error;
  $("error").textContent = error ? errorText(errorCode, error, t) : "";
  $("warnings").hidden = !status?.warnings?.length;
  $("warnings").textContent = warningText(status, t);
  $("setup").hidden = !!status || busy;
  $("connected").hidden = !status;
  $("toggle").disabled =
    busy || !status || (!status.enabled && !status.live_available);
  $("toggle").setAttribute("aria-checked", String(!!status?.enabled));
  for (const id of ["save", "refresh", "reconnect"]) $(id).disabled = busy;
  if (busy) {
    $("state-label").textContent = t("Checking changes");
    $("state-detail").textContent = t("Please wait");
    return;
  }
  if (!status) {
    $("state-label").textContent = t("Status needs checking");
    $("state-detail").textContent = t("Connection unverified");
    $("mode-description").textContent =
      t("Connect the local helper to get started.");
    $("state-dot").className = "dot";
    $("footer-status").textContent = t("ON/OFF status unverified");
    return;
  }
  $("state-label").textContent = status.enabled
    ? t("ON · Jev instructions applied")
    : t("OFF · Instructions inactive");
  $("state-detail").textContent = t("For new Aside tasks");
  $("state-dot").className = status.enabled ? "dot on" : "dot";
  $("mode-description").textContent = status.enabled
    ? t("Tasks are instructed to ask Jev to choose actions.")
    : t("Turn on to apply Jev instructions to browser tasks.");
  $("profile").textContent = status.profile_label || t("Profile selected during setup");
  $("key-status").textContent = status.live_available
    ? t("Configured · auth unverified")
    : t("API key required");
  $("model").textContent = status.model || "jev-latest";
  $("confidence").value = status.min_confidence;
  $("timeout").value = status.timeout_s;
  $("mcp-status").textContent = status.mcp_registration === "configured"
    ? t("Registered · connection unverified")
    : t("Connect in Aside settings");
  $("footer-status").textContent = t("Local helper connected");
  $("scope-note").textContent = status.enabled
    ? t("Use Jev MCP in a new task. Running tasks are not switched automatically.")
    : t("While OFF, this extension’s Jev MCP rejects new decisions. Enable it before starting a new task.");
}

function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
}
$("toggle").addEventListener("click", () => controller.toggle());
$("refresh").addEventListener("click", () => controller.refresh());
$("reconnect").addEventListener("click", () => controller.refresh());
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
$("language-select").value = i18n.language;
$("language-select").addEventListener("change", () => {
  const drafts = [$("confidence").value, $("timeout").value];
  i18n.setLanguage($("language-select").value);
  i18n.apply();
  render(controller.state);
  [$("confidence").value, $("timeout").value] = drafts;
  $("extension-id").textContent = runtime?.id || t("Available after installing the extension");
  $("toast").hidden = true;
  document.querySelectorAll("input").forEach((field) => field.setCustomValidity(""));
});
i18n.apply();
controller.refresh();
