import test from "node:test";
import assert from "node:assert/strict";
import { KeychainForm, keyErrorText } from "../extension/keychain-form.mjs";
const status = { keychain_ui_supported: true, live_available: true, credential_store: "keychain", key_status: "configured" };

test("키 저장 확인 후에만 성공 표시하고 요청 객체에서도 키를 제거한다", async () => {
  let finish, request;
  const snapshots = [];
  const form = new KeychainForm((message) => {
    request = message;
    return new Promise(resolve => { finish = resolve; });
  }, state => snapshots.push(JSON.stringify(state)));
  form.state.status = status;
  const pending = form.save("fixture-private");
  assert.equal(request.op, "set_api_key");
  assert.equal(request.secret, "fixture-private");
  assert.equal(form.state.saved, false);
  assert.equal(await form.save("second-fixture"), false);
  finish({ ok: true, status });
  assert.equal(await pending, true);
  assert.equal(form.state.saved, true);
  assert.equal(Object.hasOwn(request, "secret"), false);
  assert.ok(snapshots.every(s => !s.includes("fixture-private")));
});

test("빈 키와 공백 키는 전송하지 않는다", async () => {
  const form = new KeychainForm(() => assert.fail("must not send"));
  form.state.status = status;
  for (const key of ["", "with space", "line\nbreak", "x".repeat(4097), "한글"]) {
    assert.equal(await form.save(key), false);
    assert.equal(form.state.errorCode, "key_format");
  }
});

test("연결 확인 전 및 지원하지 않는 플랫폼에서 저장하지 않는다", async () => {
  const form = new KeychainForm(() => assert.fail("must not send"));
  assert.equal(await form.save("fixture"), false);
  form.state.status = { ...status, keychain_ui_supported: false };
  assert.equal(await form.save("fixture"), false);
});

test("키체인 오류에 응답 원문을 표시하지 않고 재확인 전 저장을 막는다", async () => {
  const form = new KeychainForm(async () => ({ ok: false, error: { code: "keychain_access", message: "fixture-private" } }));
  form.state.status = status;
  assert.equal(await form.save("fixture-private"), false);
  assert.equal(form.state.status, null);
  assert.equal(form.state.saved, false);
  assert.ok(!JSON.stringify(form.state).includes("fixture-private"));
  assert.match(keyErrorText(form.state.errorCode, x => x), /cancelled or denied/);
});

test("타임아웃에서 자동 재전송과 저장 성공 주장을 하지 않는다", async () => {
  let calls = 0;
  const form = new KeychainForm(async () => { calls++; throw Object.assign(new Error("fixture-private"), { code: "native_timeout" }); });
  form.state.status = status;
  assert.equal(await form.save("fixture-private"), false);
  assert.equal(await form.save("fixture-private"), false);
  assert.equal(calls, 1);
  assert.equal(form.state.saved, false);
  assert.ok(!JSON.stringify(form.state).includes("fixture-private"));
  assert.match(keyErrorText(form.state.errorCode, x => x), /unknown/);
});

test("키 저장 후 상태 확인 실패를 성공으로 표시하지 않는다", async () => {
  const form = new KeychainForm(async () => ({ ok: true, status: { ...status, key_status: "keychain_error" } }));
  form.state.status = status;
  assert.equal(await form.save("fixture"), false);
  assert.equal(form.state.saved, false);
});
