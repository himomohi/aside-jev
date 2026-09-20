export const HOST_NAME = "com.aside_jev.control";

export class ExtensionController {
  constructor(transport, changed = () => {}) {
    this.transport = transport;
    this.changed = changed;
    this.state = { status: null, busy: false, error: null, errorCode: null };
  }

  async request(message) {
    if (this.state.busy) return false;
    this.state.busy = true;
    this.state.error = null;
    this.state.errorCode = null;
    this.changed(this.state);
    try {
      const response = await this.transport(message);
      if (!response?.ok)
        throw Object.assign(new Error(response?.error?.message || "Check the local helper connection."), { code: response?.error?.code || "host_error" });
      const status = response.status;
      if (
        !status ||
        typeof status.enabled !== "boolean" ||
        typeof status.live_available !== "boolean"
      )
        throw Object.assign(new Error("The helper response is invalid. Check its version."), { code: "invalid_response" });
      // 호스트의 적용 결과를 받은 뒤에만 ON/OFF를 바꾼다.
      this.state.status = status;
      return true;
    } catch (error) {
      this.state.error = error.message || "Check the local helper connection.";
      this.state.errorCode = error.code || "host_error";
      // 실패 후 이전 ON 표시를 현재 상태처럼 보여 주지 않는다.
      this.state.status = null;
      return false;
    } finally {
      this.state.busy = false;
      this.changed(this.state);
    }
  }

  refresh() {
    return this.request({ op: "status" });
  }
  toggle() {
    if (!this.state.status || this.state.busy) return Promise.resolve(false);
    return this.request({
      op: "set_enabled",
      enabled: !this.state.status.enabled,
    });
  }
  configure(min_confidence, timeout_s) {
    return this.request({ op: "configure", min_confidence, timeout_s });
  }
}

export function nativeTransport(runtime) {
  return (message) =>
    new Promise((resolve, reject) => {
      if (!runtime?.sendNativeMessage) {
        reject(
          Object.assign(new Error("Install the extension in Aside and connect the local helper."), { code: "native_unavailable" }),
        );
        return;
      }
      const timer = setTimeout(
        () =>
          reject(
            Object.assign(new Error("The local helper did not respond. Refresh its status before retrying."), { code: "native_timeout" }),
          ),
        15000,
      );
      runtime.sendNativeMessage(HOST_NAME, message, (response) => {
        clearTimeout(timer);
        if (runtime.lastError)
          reject(
            Object.assign(new Error("Could not connect to the local helper. Follow the setup guide, then check again."), { code: "native_connection" }),
          );
        else resolve(response);
      });
    });
}
