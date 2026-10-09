import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createPaymentAccountStorage, clearPaymentAccountStorage } from "../lib/payment-account-storage.ts";
import { ensureClientRequestIntent, readClientRequestIntent, saveClientRequestIntent } from "../lib/client-request-intent.ts";

const KEY = "wod-web-pending-recharge";
const INTENT = "wod-web-recharge-request-intent";
class MemoryStorage {
  values = new Map<string, string>();
  get length() { return this.values.size; }
  key(index: number) { return [...this.values.keys()][index] ?? null; }
  getItem(key: string) { return this.values.get(key) ?? null; }
  setItem(key: string, value: string) { this.values.set(key, value); }
  removeItem(key: string) { this.values.delete(key); }
}

test("a reload restores the same account’s order and uncertain request intent", () => {
  const local = new MemoryStorage(), session = new MemoryStorage();
  const first = createPaymentAccountStorage(11, local, session, () => "login-a");
  first.local.setItem(KEY, "ORDER-A");
  const intent = ensureClientRequestIntent(null, "10.00|wxpay", "recharge", () => "00000000-0000-4000-8000-000000000001");
  saveClientRequestIntent(first.session, INTENT, intent);
  first.dispose();
  const reload = createPaymentAccountStorage(11, local, session, () => "unused");
  assert.equal(reload.local.getItem(KEY), "ORDER-A");
  assert.deepEqual(readClientRequestIntent(reload.session, INTENT), intent);
  first.local.setItem(KEY, "late-response");
  assert.equal(reload.local.getItem(KEY), "ORDER-A");
});

test("account B never receives A’s pending order, refund intent or late write", () => {
  const local = new MemoryStorage(), session = new MemoryStorage();
  const a = createPaymentAccountStorage(11, local, session, () => "login-a");
  a.local.setItem(KEY, "ORDER-A");
  a.session.setItem(INTENT, "intent-a");
  a.session.setItem("wod-web-refund-request-intent:ORDER-A", "refund-a");
  const b = createPaymentAccountStorage(22, local, session, () => "login-b");
  assert.equal(b.local.getItem(KEY), null);
  assert.equal(b.session.getItem(INTENT), null);
  assert.equal(b.session.getItem("wod-web-refund-request-intent:ORDER-A"), null);
  b.local.setItem(KEY, "ORDER-B");
  a.local.setItem(KEY, "LATE-A");
  a.local.removeItem(KEY);
  assert.equal(a.isCurrent(), false);
  assert.equal(b.local.getItem(KEY), "ORDER-B");
});

test("logout invalidates outstanding operations even if the same user logs in again", () => {
  const local = new MemoryStorage(), session = new MemoryStorage();
  const a = createPaymentAccountStorage(11, local, session, () => "login-a");
  a.local.setItem(KEY, "ORDER-A");
  a.session.setItem(INTENT, "intent-a");
  local.setItem("locale", "en");
  clearPaymentAccountStorage(local, session);
  const next = createPaymentAccountStorage(11, local, session, () => "login-b");
  assert.equal(a.isCurrent(), false);
  assert.equal(next.local.getItem(KEY), null);
  assert.equal(next.session.getItem(INTENT), null);
  assert.equal(local.getItem("locale"), "en");
});

test("legacy unowned cache is not adopted by the account that next opens the wallet", () => {
  const local = new MemoryStorage(), session = new MemoryStorage();
  local.setItem(KEY, "old-order");
  session.setItem(INTENT, "old-intent");
  session.setItem("wod-web-refund-request-intent:OLD-ORDER", "old-refund");
  const account = createPaymentAccountStorage(22, local, session, () => "login-b");
  assert.equal(account.local.getItem(KEY), null);
  assert.equal(account.session.getItem(INTENT), null);
  assert.equal(local.getItem(KEY), null);
  assert.equal(session.length, 0);
});

test("a separate browser tab detects logout through the shared owner marker", async () => {
  const local = new MemoryStorage(), session = new MemoryStorage();
  const a = createPaymentAccountStorage(11, local, session, () => "login-a");
  a.local.setItem(KEY, "ORDER-A");
  const moduleUrl = new URL("../lib/payment-account-storage.ts?other-tab", import.meta.url).href;
  const otherTab = await import(moduleUrl);
  const b = otherTab.createPaymentAccountStorage(22, local, new MemoryStorage(), () => "login-b");
  assert.equal(a.isCurrent(), false);
  a.local.setItem(KEY, "late-a");
  assert.equal(b.local.getItem(KEY), null);
});

test("wallet uses authenticated ownership and checks it before processing recharge responses", () => {
  const wallet = readFileSync(new URL("../components/payment-workspace.tsx", import.meta.url), "utf8");
  const shell = readFileSync(new URL("../components/product-shell.tsx", import.meta.url), "utf8");
  const api = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");
  assert.match(shell, /AuthenticatedAccount value=\{user.id\}/);
  assert.match(wallet, /createPaymentAccountStorage\(userId\)/);
  assert.doesNotMatch(wallet, /(?:localStorage|sessionStorage)\.(?:getItem|setItem|removeItem)/);
  assert.match(wallet, /await createRechargePayment\([^;]+;\s+if \(!account.isCurrent\(\)\) return;/);
  assert.match(wallet, /await getRechargePayment\(orderNo\);\s+if \(!account.isCurrent\(\)\) return;/);
  assert.match(wallet, /reason.status === 403 \|\| reason.status === 404/);
  assert.match(api, /function logoutCurrentUser\(\) \{\s+clearPaymentAccountStorage\(\);/);
});

test("unavailable browser storage permits current-session work without adopting cached data", () => {
  const unavailable = new MemoryStorage();
  unavailable.setItem = () => { throw new Error("QuotaExceededError"); };
  const account = createPaymentAccountStorage(11, unavailable, new MemoryStorage(), () => "login-a");
  assert.equal(account.isCurrent(), true);
  account.local.setItem(KEY, "ORDER-A");
  assert.equal(account.local.getItem(KEY), null);
  account.dispose();
  assert.equal(account.isCurrent(), false);
});
