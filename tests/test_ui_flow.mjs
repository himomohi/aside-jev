import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// 실제 모듈의 이벤트/상태 전환을 네트워크 없는 최소 DOM에서 검사한다. 시각 검증은 별도다.
function surface(path) {
  const elements = [];
  const ids = new Map();
  class Element {
    constructor(tag) {
      this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {}; this.attributes = {}; this.events = {};
      this.value = ""; this.hidden = false; this.disabled = false; this.open = false; this.className = "";
      this.classList = { add() {}, remove() {}, toggle() {} };
      this.elements = []; this.willValidate = false;
      elements.push(this);
    }
    get textContent() { return this.text || this.children.map((child) => child.textContent).join(""); }
    set textContent(text) { this.text = String(text); this.children = []; }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.text = ""; this.children = children; }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    getAttribute(key) { return this.attributes[key]; }
    addEventListener(name, handler) { (this.events[name] ??= []).push(handler); }
    async emit(name) { for (const handler of this.events[name] || []) await handler({ preventDefault() {} }); }
    setCustomValidity(value) { this.validationMessage = value; }
    reportValidity() { return true; }
    showModal() { this.open = true; }
    close() { this.open = false; }
    scrollIntoView() {}
    focus() {}
  }
  const html = readFileSync(new URL(path, import.meta.url), "utf8");
  for (const match of html.matchAll(/<([\w-]+)\s[^>]*\bid="([^"]+)"[^>]*>/g)) {
    const element = new Element(match[1]);
    element.value = match[0].match(/\bvalue="([^"]*)"/)?.[1] ?? "";
    ids.set(match[2], element);
  }
  const mock = new Element("input"); mock.value = "mock";
  const live = ids.get("live-mode");
  const providers = [mock, live].filter(Boolean);
  const document = {
    documentElement: { lang: "en" }, body: new Element("body"),
    getElementById(id) { assert.ok(ids.has(id), `missing element: ${id}`); return ids.get(id); },
    createElement(tag) { return new Element(tag); }, addEventListener() {},
    querySelector() { return mock; },
    querySelectorAll(selector) {
      if (selector === 'input[name="provider"]') return providers;
      if (selector.startsWith(".")) return elements.filter((el) => el.className.split(" ").includes(selector.slice(1)));
      if (selector === "input, textarea") return elements.filter((el) => ["INPUT", "TEXTAREA"].includes(el.tagName));
      if (selector === "input") return elements.filter((el) => el.tagName === "INPUT");
      return [];
    },
  };
  return { document, get: (id) => ids.get(id) };
}
function installGlobals(t, values) {
  for (const [key, value] of Object.entries(values)) {
    const previous = Object.getOwnPropertyDescriptor(globalThis, key);
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
    t.after(() => previous ? Object.defineProperty(globalThis, key, previous) : delete globalThis[key]);
  }
}
const settle = () => new Promise((resolve) => setImmediate(resolve));

test("대시보드 실제 이벤트: 영어 시작, 오류 번역, 목표와 설정 초안 보존", async (t) => {
  const { document, get } = surface("../src/aside_jev/static/index.html");
  const storage = new Map();
  installGlobals(t, {
    document,
    localStorage: { getItem: (key) => storage.get(key), setItem: (key, value) => storage.set(key, value) },
    fetch: async (url) => url === "/api/config"
      ? { ok: true, json: async () => ({ version: "test", live_available: false, session_token: "test" }) }
      : { ok: false, json: async () => ({ code: "configuration", error: "백엔드 원문" }) },
  });
  await import("../src/aside_jev/static/app.js?flow-test");
  await settle();
  assert.equal(get("language-select").value, "en");
  assert.match(get("goal").value, /^Choose the next action/);
  assert.equal(get("live-mode").disabled, true);
  await get("decision-form").emit("submit");
  assert.match(get("error-message").textContent, /^Set TYPESAFE_API_KEY/);
  get("language-select").value = "ko";
  await get("language-select").emit("change");
  assert.equal(document.documentElement.lang, "ko");
  assert.match(get("goal").value, /^비어 있는/);
  assert.match(get("error-message").textContent, /^서버에 TYPESAFE_API_KEY/);
  get("goal").value = "Keep my custom goal";
  await get("settings-button").emit("click");
  get("observation-input").value = '{"custom":"관찰 유지"}';
  get("candidates-input").value = '[{"id":"my-action","description":"keep this"}]';
  get("language-select").value = "en";
  await get("language-select").emit("change");
  assert.equal(get("goal").value, "Keep my custom goal");
  assert.equal(get("observation-input").value, '{"custom":"관찰 유지"}');
  assert.equal(get("candidates-input").value, '[{"id":"my-action","description":"keep this"}]');
  assert.deepEqual([...storage], [["aside-jev.dashboard.language", "en"]]);
});

test("팝업 실제 이벤트: 네이티브 미연결 오류 번역과 설정 초안 보존", async (t) => {
  const { document, get } = surface("../extension/popup.html");
  installGlobals(t, { document, localStorage: { getItem: () => null, setItem() {} }, chrome: undefined });
  await import("../extension/popup.js?flow-test");
  await settle();
  assert.equal(get("language-select").value, "auto");
  assert.match(get("error").textContent, /^Install the extension in Aside/);
  assert.equal(get("toggle").disabled, true);
  get("confidence").value = "0.95";
  get("timeout").value = "25";
  get("language-select").value = "ko";
  await get("language-select").emit("change");
  assert.equal(document.documentElement.lang, "ko");
  assert.match(get("error").textContent, /^Aside에 확장을 설치/);
  assert.equal(get("confidence").value, "0.95");
  assert.equal(get("timeout").value, "25");
});

test("키 입력 창: 비밀번호 입력을 즉시 지우고 키를 저장소와 UI에 노출하지 않는다", async (t) => {
  const { document, get } = surface("../extension/keychain.html");
  const storage = new Map(), events = {};
  let closed = false, complete, pendingMessage;
  const keyStatus = { keychain_ui_supported: true, live_available: false, credential_store: 'keychain', key_status: 'missing' };
  installGlobals(t, {
    document,
    localStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) },
    window: { addEventListener: (name, action) => { events[name] = action; }, close: () => { closed = true; } },
    chrome: { runtime: { sendNativeMessage: (_host, message, callback) => {
      if (message.op === 'status') callback({ok: true, status: keyStatus});
      else { complete = callback; pendingMessage = message; }
    } } },
  });
  await import('../extension/keychain.js?ui-test');
  await settle();
  assert.equal(get('api-key').disabled, false);
  get('api-key').value = 'fixture-secret-private';
  const saving = get('key-form').emit('submit');
  assert.equal(get('api-key').value, '');
  assert.equal(get('save-key').disabled, true);
  assert.equal(get('cancel').disabled, true);
  complete({ok: true, status: {...keyStatus, live_available: true, key_status: 'configured'}});
  await saving;
  assert.equal(get('key-result').hidden, false);
  assert.equal(pendingMessage.secret, undefined);
  assert.equal(storage.size, 0);
  get('api-key').value = 'unsaved-fixture';
  events.pagehide();
  assert.equal(get('api-key').value, '');
  await get('cancel').emit('click');
  assert.equal(closed, true);
});

test("로컬 MCP 진단 성공은 세션 연결로 승격하지 않고 수동 요청과 실패 복구를 보존한다", async (t) => {
  const { document, get } = surface("../extension/popup.html");
  const calls = [], windows = [];
  let complete;
  const status = {
    enabled: true, live_available: true, keychain_ui_supported: true,
    min_confidence: 0.7, timeout_s: 15, mcp_registration: "configured", mcp_connected: null,
    connection_check: { state: "unverified", code: "not_checked", checked_at: null, tool_count: 0, scope: "local_mcp_probe" },
  };
  installGlobals(t, {
    document, localStorage: { getItem: () => null, setItem() {} },
    chrome: { runtime: { id: "fixture-extension", getURL: path => `chrome-extension://fixture/${path}`,
      sendNativeMessage: (_host, message, callback) => {
        calls.push(message);
        if (message.op === "check_connection") complete = callback;
        else callback({ ok: true, status });
      },
    }, windows: { create: async options => windows.push(options) } },
  });
  await import("../extension/popup.js?connection-flow-test");
  await settle();
  assert.deepEqual(calls, [{ op: "status" }]);
  assert.equal(get("mcp-status").textContent, "Registered");
  assert.equal(get("probe-status").textContent, "Not checked");
  assert.equal(get("session-status").textContent, "Unverified");
  assert.equal(get("open-keychain").hidden, false);
  assert.equal(get("open-keychain").getAttribute("aria-label"), "Replace API key");
  get("diagnostics").hidden = true;
  get("settings").hidden = true;
  await get("settings-button").emit("click");
  assert.equal(get("settings").hidden, false);
  assert.equal(get("settings-button").getAttribute("aria-expanded"), "true");
  await get("info-button").emit("click");
  assert.equal(get("settings").hidden, true);
  assert.equal(get("diagnostics").hidden, false);
  await get("info-button").emit("click");
  assert.equal(get("diagnostics").hidden, true);
  await get("open-keychain").emit("click");
  assert.equal(windows[0].url, "chrome-extension://fixture/keychain.html");
  const checking = get("check-connection").emit("click");
  assert.equal(get("probe-status").textContent, "Checking…");
  assert.equal(get("check-connection").disabled, true);
  assert.equal(get("toggle").disabled, true);
  // 프로그램으로 중복 이벤트를 보내도 네이티브 요청은 하나다.
  await get("check-connection").emit("click");
  assert.deepEqual(calls, [{ op: "status" }, { op: "check_connection" }]);
  status.connection_check = { state: "ready", code: "ok", checked_at: "2026-09-21T10:00:00Z", tool_count: 6, scope: "local_mcp_probe" };
  complete({ ok: true, status });
  await checking;
  assert.equal(get("probe-status").textContent, "Ready · local only");
  assert.equal(get("session-status").textContent, "Unverified");
  assert.equal(get("probe-recovery").hidden, true);
  assert.match(get("probe-detail").textContent, /tools: 6/);
  get("language-select").value = "ko";
  await get("language-select").emit("change");
  assert.equal(get("probe-status").textContent, "준비됨 · 로컬만");
  assert.equal(get("session-status").textContent, "미확인");
  const retry = get("check-connection").emit("click");
  status.connection_check = { ...status.connection_check, state: "failed", code: "probe_timeout", tool_count: 0 };
  complete({ ok: true, status });
  await retry;
  assert.equal(get("probe-status").textContent, "진단 실패");
  assert.equal(get("diagnostics").hidden, false);
  assert.equal(get("probe-recovery").hidden, false);
  assert.equal(get("toggle").getAttribute("aria-checked"), "true");
  assert.equal(get("session-status").textContent, "미확인");
  status.connection_check = { ...status.connection_check, state: "ready", scope: "unknown" };
  await get("refresh").emit("click");
  assert.equal(get("probe-status").textContent, "진단 전");
});


test("팝오버 컨트롤 ID는 고유하다", () => {
  const html = readFileSync(new URL("../extension/popup.html", import.meta.url), "utf8");
  const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
  assert.equal(new Set(ids).size, ids.length);
});
