import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createI18n as workspaceI18n, messages as workspaceMessages } from "../src/aside_jev/static/i18n.mjs";
import { createI18n as popupI18n, messages as popupMessages } from "../extension/i18n.mjs";
import { demo, migrateDemo, displayDescription } from "../src/aside_jev/static/demo.mjs";
import { errorText, warningText } from "../extension/errors.mjs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const decode = (value) => value.replaceAll("&amp;", "&").replaceAll("&quot;", '"').replaceAll("&#x27;", "'");
for (const [name, createI18n, messages, path] of [
  ["dashboard", workspaceI18n, workspaceMessages, "../src/aside_jev/static/index.html"],
  ["popup", popupI18n, popupMessages, "../extension/popup.html"],
  ["keychain", popupI18n, popupMessages, "../extension/keychain.html"],
]) {
  test(`${name}: 영어 기본, 명시적 언어만 저장, 저장 실패 복구`, () => {
    const values = new Map();
    const storage = { getItem: (key) => values.get(key), setItem: (key, value) => values.set(key, value) };
    const i18n = createI18n("language", storage);
    assert.equal(i18n.language, "en");
    i18n.setLanguage("ko");
    assert.equal(i18n.t("Language"), "언어");
    assert.equal(createI18n("language", storage).language, "ko");
    assert.deepEqual([...values], [["language", "ko"]]);
    i18n.setLanguage("ja");
    assert.equal(i18n.language, "en");
    const blocked = createI18n("language", { getItem() { throw Error(); }, setItem() { throw Error(); } });
    assert.equal(blocked.language, "en");
    assert.equal(blocked.setLanguage("ko"), "ko");
  });
  test(`${name}: HTML 언어, 문구, 접근성 속성과 사전 일치`, () => {
    const html = read(path);
    assert.match(html, /<html lang="en">/);
    assert.match(html, /id="language-select"/);
    assert.deepEqual(Object.keys(messages.en).sort(), Object.keys(messages.ko).sort());
    for (const match of html.matchAll(/data-i18n(?:-(?:aria-label|placeholder|title))?="([^"]+)"/g)) {
      const key = decode(match[1]);
      assert.ok(messages.en[key], `missing English key: ${key}`);
      assert.ok(messages.ko[key], `missing Korean key: ${key}`);
      assert.deepEqual(messages.en[key].match(/\{\w+\}/g), messages.ko[key].match(/\{\w+\}/g));
    }
    assert.equal((html.match(/[가-힣]+/g) || []).join(""), "한국어");
  });
  test(`${name}: lang, aria-label, placeholder를 같이 변경`, () => {
    const i18n = createI18n("language", null);
    const text = { dataset: { i18n: "Language" }, textContent: "" };
    const attributes = { "data-i18n-aria-label": "Language", "data-i18n-placeholder": "Language", "data-i18n-title": "Language" };
    const input = { getAttribute: (name) => attributes[name], setAttribute: (name, value) => { attributes[name] = value; } };
    const root = { documentElement: {}, querySelectorAll: (selector) => selector === "[data-i18n]" ? [text] : [input] };
    i18n.setLanguage("ko");
    i18n.apply(root);
    assert.equal(root.documentElement.lang, "ko");
    assert.equal(text.textContent, "언어");
    assert.equal(attributes["aria-label"], "언어");
    assert.equal(attributes.placeholder, "언어");
    assert.equal(attributes.title, "언어");
    i18n.setLanguage("en");
    i18n.apply(root);
    assert.equal(root.documentElement.lang, "en");
    assert.equal(text.textContent, "Language");
  });
}

test("기본 예시는 번역하지만 사용자가 편집한 JSON은 보존한다", () => {
  const english = demo((key) => workspaceMessages.en[key]);
  const korean = demo((key) => workspaceMessages.ko[key]);
  assert.notEqual(english.observation.title, korean.observation.title);
  assert.deepEqual(migrateDemo(english, english, korean), korean);
  const custom = { ...structuredClone(english), model: "custom-model" };
  custom.observation.note = "사용자가 작성한 관찰";
  custom.candidates[0].arguments.text = "User input";
  assert.deepEqual(migrateDemo(custom, english, korean), custom);
  assert.equal(displayDescription(english.candidates[0], "ko", workspaceMessages), korean.candidates[0].description);
  assert.equal(displayDescription(custom.candidates[0], "ko", workspaceMessages), custom.candidates[0].description);
});

test("도우미 오류는 code로 번역하고 미분류 원문은 경계를 명시한다", () => {
  const i18n = popupI18n("language", null);
  assert.match(errorText("key_missing", "서버 원문", i18n.t), /Configure a TypeSafe/);
  assert.doesNotMatch(errorText("key_missing", "서버 원문", i18n.t), /서버 원문/);
  assert.match(errorText("future_error", "Original detail", i18n.t), /^Backend detail \(original\): Original detail$/);
  assert.match(warningText({ warnings: ["옛 규칙"] }, i18n.t), /global files were not changed/);
  i18n.setLanguage("ko");
  assert.match(errorText("key_missing", "서버 원문", i18n.t), /API 키/);
});

test("manifest 지역화는 기존 nativeMessaging 권한만 유지한다", () => {
  const manifest = JSON.parse(read("../extension/manifest.json"));
  assert.equal(manifest.default_locale, "en");
  assert.deepEqual(manifest.permissions, ["nativeMessaging"]);
  for (const language of ["en", "ko"]) {
    const messages = JSON.parse(read(`../extension/_locales/${language}/messages.json`));
    for (const value of [manifest.name, manifest.description, manifest.action.default_title]) {
      assert.ok(messages[value.match(/^__MSG_(\w+)__$/)[1]]?.message);
    }
  }
});

test("독립 배포되는 대시보드와 확장의 번역 사전은 동일하다", () => {
  assert.deepEqual(workspaceMessages, popupMessages);
});

const { createExtensionI18n } = await import('../extension/region-locale.mjs');
test('IP 자동 언어: 한국과 해외, 쿠키 미전송, IP 미저장', async () => {
  for (const [country, expected] of [['KR', 'ko'], ['US', 'en'], ['JP', 'en']]) {
    const saved = new Map();
    const i18n = createExtensionI18n({getItem: k => saved.get(k), setItem: (k,v) => saved.set(k,v)});
    await i18n.resolve({fetcher: async (url, options) => {
      assert.equal(url, 'https://api.country.is/');
      assert.equal(options.credentials, 'omit');
      assert.equal(options.referrerPolicy, 'no-referrer');
      return {ok:true,json:async()=>({country,ip:'test-only'})};
    }});
    assert.equal(i18n.language, expected);
    assert.equal(saved.size, 0);
  }
});
test('IP 조회 실패와 잘못된 응답은 브라우저 언어로 복구', async () => {
  for (const fetcher of [async()=>{throw Error('offline')}, async()=>({ok:true,json:async()=>({country:123})})]) {
    const i18n=createExtensionI18n(null);
    await i18n.resolve({fetcher,browserLanguage:'ko-KR'});
    assert.equal(i18n.language,'ko');
  }
});
test('IP 응답이 늦게 와도 수동 언어 선택을 덮어쓰지 않는다', async () => {
  let finish;
  const i18n=createExtensionI18n(null);
  const pending=i18n.resolve({fetcher:()=>new Promise(resolve=>{finish=resolve})});
  i18n.setLanguage('en');
  finish({ok:true,json:async()=>({country:'KR'})});
  await pending;
  assert.equal(i18n.language,'en');
  let requested=false;
  await i18n.resolve({fetcher:async()=>{requested=true}});
  assert.equal(requested,false);
});
