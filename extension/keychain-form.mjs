// 키 원문은 상태, 오류 메시지, 저장소에 넣지 않는다.
const safeCode = (code) => new Set([
  "key_format", "keychain_access", "keychain_platform", "keychain_verify",
  "keychain_rollback", "keychain_cleanup", "keychain_unavailable",
  "native_timeout", "busy", "operation", "invalid_response",
]).has(code) ? code : "internal";

export class KeychainForm {
  constructor(transport, changed = () => {}) {
    this.transport = transport;
    this.changed = changed;
    this.state = { busy: false, status: null, errorCode: null, saved: false };
  }

  async request(message) {
    if (this.state.busy) {
      delete message.secret;
      return false;
    }
    const saving = message.op === "set_api_key";
    this.state.busy = true;
    this.state.errorCode = null;
    this.state.saved = false;
    this.changed(this.state);
    try {
      const response = await this.transport(message);
      if (!response?.ok) {
        this.state.errorCode = safeCode(response?.error?.code);
        this.state.status = null;
        return false;
      }
      const status = response.status;
      if (typeof status?.keychain_ui_supported !== "boolean" || typeof status?.live_available !== "boolean") {
        this.state.errorCode = "invalid_response";
        this.state.status = null;
        return false;
      }
      this.state.status = {
        keychain_ui_supported: status.keychain_ui_supported,
        live_available: status.live_available,
        credential_store: status.credential_store === "keychain" ? "keychain" : "env_file",
        key_status: ["configured", "missing", "keychain_error"].includes(status.key_status) ? status.key_status : "unknown",
      };
      if (saving && (status.credential_store !== "keychain" || status.key_status !== "configured")) {
        this.state.errorCode = "keychain_unavailable";
        return false;
      }
      this.state.saved = saving;
      return true;
    } catch (error) {
      // 예외 원문에는 입력값이 섞일 수 있다. 고정 코드만 표시한다.
      this.state.errorCode = safeCode(error?.code);
      this.state.status = null;
      return false;
    } finally {
      delete message.secret;
      this.state.busy = false;
      this.changed(this.state);
    }
  }

  refresh() { return this.request({ op: "status" }); }

  save(secret) {
    if (this.state.busy) return Promise.resolve(false);
    if (!this.state.status?.keychain_ui_supported) return Promise.resolve(false);
    if (typeof secret !== "string" || !/^[\x21-\x7e]{1,4096}$/.test(secret)) {
      this.state.errorCode = "key_format";
      this.state.saved = false;
      this.changed(this.state);
      return Promise.resolve(false);
    }
    return this.request({ op: "set_api_key", secret });
  }
}

export function keyErrorText(code, t) {
  const messages = {
    key_format: "Enter a valid API key without spaces (up to 4096 characters).",
    keychain_access: "Keychain access was cancelled or denied. Unlock your Keychain, refresh the status, then try again.",
    keychain_platform: "Keychain input is available only on macOS.",
    keychain_verify: "The saved key could not be verified. Refresh the status before trying again.",
    keychain_rollback: "The previous key could not be restored. Check Aside Jev in Keychain Access before continuing.",
    keychain_cleanup: "The key was saved, but an old key file could not be removed. Review the legacy file before continuing.",
    native_timeout: "Saving status is unknown. Check for a macOS approval dialog, then refresh the status. Do not submit again while approval is pending.",
    busy: "Another update is running. Wait, then refresh the status.",
    operation: "Update the local helper to use this key window.",
  };
  return t(Object.hasOwn(messages, code) ? messages[code] : "Could not confirm the Keychain operation. Refresh the status and check the local helper.");
}
