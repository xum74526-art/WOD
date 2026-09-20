import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  clearClientRequestIntent,
  clientRequestFingerprint,
  ensureClientRequestIntent,
  readClientRequestIntent,
  saveClientRequestIntent,
} from "../lib/client-request-intent.ts";

class MemoryStorage {
  private readonly values = new Map<string, string>();
  getItem(key: string) { return this.values.get(key) ?? null; }
  setItem(key: string, value: string) { this.values.set(key, value); }
  removeItem(key: string) { this.values.delete(key); }
}

test("a money-movement intent reuses its request id until the payload changes", () => {
  const firstFingerprint = clientRequestFingerprint(["100.00", "alipay"]);
  const first = ensureClientRequestIntent(null, firstFingerprint, "recharge", () => "00000000-0000-4000-8000-000000000001");
  const retry = ensureClientRequestIntent(first, firstFingerprint, "recharge", () => "00000000-0000-4000-8000-000000000002");
  const changed = ensureClientRequestIntent(first, clientRequestFingerprint(["200.00", "alipay"]), "recharge", () => "00000000-0000-4000-8000-000000000003");

  assert.equal(retry.requestId, first.requestId);
  assert.notEqual(changed.requestId, first.requestId);
});

test("session storage preserves an uncertain intent across a page reload", () => {
  const storage = new MemoryStorage();
  const intent = ensureClientRequestIntent(null, "withdrawal:10:7", "withdrawal", () => "00000000-0000-4000-8000-000000000004");
  saveClientRequestIntent(storage, "intent", intent);

  assert.deepEqual(readClientRequestIntent(storage, "intent"), intent);
  clearClientRequestIntent(storage, "intent");
  assert.equal(readClientRequestIntent(storage, "intent"), null);
});

test("malformed stored request ids are never reused", () => {
  const storage = new MemoryStorage();
  storage.setItem("intent", JSON.stringify({ fingerprint: "same", requestId: "bad id" }));
  assert.equal(readClientRequestIntent(storage, "intent"), null);
});

test("wallet mutations persist their id before sending and clear it only after a response", () => {
  const wallet = readFileSync(new URL("../components/payment-workspace.tsx", import.meta.url), "utf8");
  const api = readFileSync(new URL("../lib/mobile-business-api.ts", import.meta.url), "utf8");
  const recharge = wallet.slice(wallet.indexOf("async function submitRecharge"), wallet.indexOf("async function submitWithdrawal"));
  const withdrawal = wallet.slice(wallet.indexOf("async function submitWithdrawal"), wallet.indexOf("async function cancel("));

  for (const [source, createCall, key] of [
    [recharge, "createRechargePayment", "RECHARGE_INTENT_KEY"],
    [withdrawal, "createWithdrawal", "WITHDRAWAL_INTENT_KEY"],
  ] as const) {
    const save = source.indexOf(`saveClientRequestIntent(storage, ${key}, intent)`);
    const create = source.indexOf(createCall, save);
    const clear = source.indexOf(`clearClientRequestIntent(storage, ${key})`, create);
    assert.ok(save >= 0 && create > save && clear > create, `${createCall} must persist, send, then clear its id`);
  }
  assert.match(api, /createRechargePayment\(amount_cny: number, payment_type: "alipay" \| "wxpay", client_request_id: string\)/);
  assert.match(api, /JSON\.stringify\(\{ amount_cny, payment_type, client_request_id \}\)/);
});
