import test from "node:test";
import assert from "node:assert/strict";
import { ExtensionController } from "../extension/controller.mjs";

const status = (enabled) => ({
  enabled,
  live_available: true,
  enforcement: "instructions_only",
  min_confidence: 0.7,
  timeout_s: 15,
});

test("호스트 확인 전 ON으로 표시하지 않고 중복 요청을 막는다", async () => {
  let finish;
  const calls = [];
  const controller = new ExtensionController((message) => {
    calls.push(message);
    return new Promise((resolve) => {
      finish = resolve;
    });
  });
  controller.state.status = status(false);
  const changing = controller.toggle();
  assert.equal(controller.state.status.enabled, false);
  assert.equal(controller.state.busy, true);
  assert.equal(await controller.toggle(), false);
  assert.equal(calls.length, 1);
  finish({ ok: true, status: status(true) });
  assert.equal(await changing, true);
  assert.equal(controller.state.status.enabled, true);
  assert.equal(controller.state.status.enforcement, "instructions_only");
});

test("저장 실패는 상태 미확인으로 표시하고 실제 OFF로 오인하지 않는다", async () => {
  const controller = new ExtensionController(async () => ({
    ok: false,
    error: { message: "수정 충돌" },
  }));
  controller.state.status = status(true);
  assert.equal(await controller.toggle(), false);
  assert.equal(controller.state.status, null);
  assert.equal(controller.state.error, "수정 충돌");
  assert.equal(controller.state.busy, false);
});

test("깨진 호스트 응답에서 ON 성공을 만들지 않는다", async () => {
  const controller = new ExtensionController(async () => ({
    ok: true,
    status: { enabled: "true" },
  }));
  assert.equal(await controller.refresh(), false);
  assert.equal(controller.state.status, null);
});

test("설정 저장 응답과 OFF 전환 결과를 반영한다", async () => {
  const calls = [];
  const controller = new ExtensionController(async (message) => {
    calls.push(message);
    return {
      ok: true,
      status: { ...status(message.op !== "set_enabled"), min_confidence: 0.9 },
    };
  });
  await controller.refresh();
  await controller.configure(0.9, 20);
  assert.deepEqual(calls[1], {
    op: "configure",
    min_confidence: 0.9,
    timeout_s: 20,
  });
  assert.equal(controller.state.status.min_confidence, 0.9);
  await controller.toggle();
  assert.equal(controller.state.status.enabled, false);
});

test("원문과 오류 코드를 분리해 언어를 바꿔도 네이티브 계약을 유지한다", async () => {
  const controller = new ExtensionController(async () => ({ ok: false, error: { code: "key_missing", message: "API 키가 없습니다" } }));
  assert.equal(await controller.refresh(), false);
  assert.equal(controller.state.errorCode, "key_missing");
  assert.equal(controller.state.error, "API 키가 없습니다");
  assert.equal(controller.state.status, null);
});
