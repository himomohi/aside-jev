import { nativeTransport } from "./controller.mjs";
import { KeychainForm, keyErrorText } from "./keychain-form.mjs";
import { createExtensionI18n } from "./region-locale.mjs";

const $ = (id) => document.getElementById(id);
const i18n = createExtensionI18n();
const t = (key) => i18n.t(key);
// 키체인 승인 중에도 창을 유지한다. 타임아웃 후 자동 재전송하지 않는다.
const form = new KeychainForm(nativeTransport(chrome.runtime, 120000), render);

function render({ busy, status, errorCode, saved }) {
  const supported = status?.keychain_ui_supported === true;
  $("api-key").disabled = busy || !supported;
  $("save-key").disabled = busy || !supported;
  $("refresh-key").disabled = busy;
  $("cancel").disabled = busy;
  $("key-form").setAttribute("aria-busy", String(busy));
  $("save-key").textContent = t(busy ? "Please wait" : "Save to Keychain");
  $("key-error").hidden = !errorCode;
  $("key-error").textContent = errorCode ? keyErrorText(errorCode, t) : "";
  $("key-result").hidden = !saved;
  $("key-result").textContent = saved ? t("Saved to macOS Keychain. Close this window, reopen Aside Jev, and turn it on when ready.") : "";
  $("key-state").textContent = t(busy ? "Waiting for the local helper or macOS approval…"
    : !status ? "Check the local connection before entering a key."
    : !supported ? "Keychain input is available only on macOS."
    : status.key_status === "keychain_error" ? "Keychain access needs attention."
    : status.live_available ? "A key is configured. Entering a new key replaces it; authentication is unverified."
    : "No API key is saved yet.");
}

$("key-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  let secret = $("api-key").value;
  // DOM에서 즉시 제거한다. 메모리 완전 소거를 보장하는 기능은 아니다.
  $("api-key").value = "";
  const pending = form.save(secret);
  secret = "";
  await pending;
  if (form.state.saved) $("cancel").focus();
  else if (!$("api-key").disabled) $("api-key").focus();
});
$("cancel").addEventListener("click", () => {
  $("api-key").value = "";
  window.close();
});
window.addEventListener("pagehide", () => { $("api-key").value = ""; });
$("refresh-key").addEventListener("click", () => form.refresh());
$("language-select").value = i18n.selection;
$("language-select").addEventListener("change", async () => {
  i18n.setLanguage($("language-select").value);
  await i18n.resolve();
  i18n.apply();
  render(form.state);
});
i18n.apply();
form.refresh().then(() => { if (!$("api-key").disabled) $("api-key").focus(); });

// 자동 감지는 사용자가 입력한 설정 초안을 덮어쓰지 않는다.
i18n.resolve().then(() => {
  i18n.apply();
  render(form.state);
});
