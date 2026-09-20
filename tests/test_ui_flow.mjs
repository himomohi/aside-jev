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
  assert.equal(get("language-select").value, "en");
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
