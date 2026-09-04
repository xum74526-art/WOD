import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  clearDeletionReceipt, DELETION_RECEIPT_KEY, deletionRevokesNormalSession, newDeletionReceipt,
  readDeletionReceipt, saveDeletionReceipt, submitDeletionWithRecovery,
  type AccountDeletionStatus,
} from "../lib/account-deletion-flow.ts";
import { accountDeletionMethods, accountDeletionProxyOptions } from "../lib/account-deletion-proxy.ts";
import { deletionMarkerMatchesTicket, deletionMayClearSession, deletionSessionMarker } from "../lib/server/account-deletion-session.ts";

function storage() {
  const values = new Map<string, string>();
  return {
    values,
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
  };
}
const ticket = "deletion-only-opaque-test-receipt-not-a-real-ticket";
const result = (status: AccountDeletionStatus["status"]): AccountDeletionStatus => ({
  status, blockers: [], completed_at: status === "completed" ? "2026-09-04T01:00:00Z" : null,
});

test("receipt-bound BFF operations work without forwarding the normal login token", () => {
  const input = { ticket, confirm: true, password: "not-forwarded", user_id: 12, token: "not-forwarded" };
  assert.deepEqual(accountDeletionMethods, { eligibility: "GET", verify: "POST", submit: "POST", status: "POST" });
  assert.deepEqual(accountDeletionProxyOptions("eligibility", input), { method: "GET", auth: true });
  assert.deepEqual(accountDeletionProxyOptions("verify", input), { method: "POST", auth: true, body: { password: "not-forwarded" } });
  assert.deepEqual(accountDeletionProxyOptions("submit", input), { method: "POST", auth: false, body: { ticket, confirm: true } });
  assert.deepEqual(accountDeletionProxyOptions("status", input), { method: "POST", auth: false, body: { ticket } });
  assert.deepEqual(accountDeletionProxyOptions("submit", { ticket, confirm: false }).body, { ticket, confirm: false });
});

test("cookies are cleared only when backend confirms processing or completed, not merely verification", () => {
  for (const status of ["verified", "blocked", "unknown"]) assert.equal(deletionRevokesNormalSession({ status }), false);
  for (const status of ["processing", "completed"]) assert.equal(deletionRevokesNormalSession({ status }), true);
  for (const value of [null, true, "completed", {}, { completed: true }]) assert.equal(deletionRevokesNormalSession(value), false);
});

test("checking account A's deletion receipt must never clear account B's current login Cookie", () => {
  const marker = deletionSessionMarker(ticket, "account-A-session");
  assert.equal(deletionMayClearSession(marker, ticket, "account-A-session"), true);
  assert.equal(deletionMayClearSession(marker, ticket, "account-B-session"), false);
  assert.equal(deletionMayClearSession(marker, "another-deletion-receipt", "account-A-session"), false);
  assert.equal(deletionMayClearSession(marker, ticket, undefined), false);
  assert.equal(deletionMayClearSession(undefined, ticket, "account-A-session"), false);
  assert.equal(deletionMayClearSession("malformed", ticket, "account-A-session"), false);
  assert.equal(deletionMarkerMatchesTicket(marker, ticket), true);
  assert.equal(deletionMarkerMatchesTicket(marker, "another-deletion-receipt"), false);
  assert.match(marker, /^[a-f0-9]{64}\.[a-f0-9]{64}$/);
  assert.equal(marker.includes("account-A-session"), false);
  assert.equal(marker.includes(ticket), false);
});

test("deletion-only recovery receipt is bounded, does not store passwords, and cleans only its own key", () => {
  const now = Date.parse("2026-09-04T00:00:00Z");
  const store = storage();
  store.setItem("unrelated-preference", "keep");
  const receipt = newDeletionReceipt({ ticket, expires_at: new Date(now + 600_000).toISOString() }, now);
  assert.equal(receipt.expiresAt, now + 7 * 86400_000);
  saveDeletionReceipt(store, receipt);
  assert.deepEqual(readDeletionReceipt(store, now), receipt);
  assert.deepEqual(Object.keys(JSON.parse(store.getItem(DELETION_RECEIPT_KEY)!)).sort(), ["expiresAt", "ticket", "verifyExpiresAt"]);
  clearDeletionReceipt(store, ticket);
  assert.equal(store.getItem(DELETION_RECEIPT_KEY), null);
  assert.equal(store.getItem("unrelated-preference"), "keep");
  const bounded = newDeletionReceipt({ ticket, expires_at: "", receipt_expires_at: new Date(now + 86400_000).toISOString() }, now);
  assert.equal(bounded.expiresAt, now + 86400_000);
});

test("a completed A receipt cannot delete the B receipt saved by another tab", () => {
  const store = storage();
  const other = { ticket: "another-account-receipt-only-not-a-real-ticket", expiresAt: Date.now() + 100_000 };
  saveDeletionReceipt(store, other);
  clearDeletionReceipt(store, ticket);
  assert.deepEqual(readDeletionReceipt(store), other);
  clearDeletionReceipt(store, other.ticket);
  assert.equal(readDeletionReceipt(store), null);
});

test("invalid snapshot cleanup cannot remove a newer valid receipt", () => {
  const store = storage();
  const other = { ticket: "another-account-receipt-only-not-a-real-ticket", expiresAt: Date.now() + 100_000 };
  store.setItem(DELETION_RECEIPT_KEY, "{invalid-old-snapshot");
  let reads = 0;
  const racingStorage = {
    ...store,
    getItem(key: string) {
      reads += 1;
      if (reads === 2) saveDeletionReceipt(store, other);
      return store.getItem(key);
    },
  };
  assert.equal(readDeletionReceipt(racingStorage), null);
  assert.deepEqual(readDeletionReceipt(store), other);
});

test("ticket-scoped cleanup rechecks the value before removing its captured receipt", () => {
  const store = storage();
  const other = { ticket: "another-account-receipt-only-not-a-real-ticket", expiresAt: Date.now() + 100_000 };
  saveDeletionReceipt(store, { ticket, expiresAt: Date.now() + 100_000 });
  let reads = 0;
  const racingStorage = {
    ...store,
    getItem(key: string) {
      reads += 1;
      if (reads === 2) saveDeletionReceipt(store, other);
      return store.getItem(key);
    },
  };
  clearDeletionReceipt(racingStorage, ticket);
  assert.deepEqual(readDeletionReceipt(store), other);
});

test("expired, malformed and overlong receipts are removed without trying a deletion", () => {
  const now = Date.now();
  for (const raw of ["{broken", JSON.stringify({ ticket, expiresAt: now }), JSON.stringify({ ticket, expiresAt: now + 8 * 86400_000 }), JSON.stringify({ ticket: "short", expiresAt: now + 1000 })]) {
    const store = storage(); store.setItem(DELETION_RECEIPT_KEY, raw);
    assert.equal(readDeletionReceipt(store, now), null);
    assert.equal(store.getItem(DELETION_RECEIPT_KEY), null);
  }
});

test("an ambiguous submit queries with the same receipt, never repeats submission or infers completion", async () => {
  const calls: string[] = [];
  const observed = await submitDeletionWithRecovery(ticket,
    async (value) => { calls.push(`submit:${value}`); throw new Error("timeout"); },
    async (value) => { calls.push(`status:${value}`); return result("processing"); });
  assert.deepEqual(calls, [`submit:${ticket}`, `status:${ticket}`]);
  assert.equal(observed.status, "processing");
});

test("when submit and status fail, receipt remains for reload/retry, not a false success", async () => {
  const store = storage();
  saveDeletionReceipt(store, { ticket, expiresAt: Date.now() + 100_000 });
  await assert.rejects(submitDeletionWithRecovery(ticket,
    async () => { throw new Error("submit timeout"); },
    async () => { throw new Error("status unavailable"); }), /status unavailable/);
  assert.equal(readDeletionReceipt(store)?.ticket, ticket);
});

test("blocked and verified responses remain non-completion and do not trigger a status request", async () => {
  for (const status of ["blocked", "verified"] as const) {
    let checked = false;
    assert.equal((await submitDeletionWithRecovery(ticket, async () => result(status), async () => { checked = true; return result("completed"); })).status, status);
    assert.equal(checked, false);
  }
});

test("public deletion entry, actual settings link and privacy notice are present", () => {
  const page = readFileSync(new URL("../app/account-deletion/page.tsx", import.meta.url), "utf8");
  const settings = readFileSync(new URL("../components/mobile-account-settings.tsx", import.meta.url), "utf8");
  const privacy = readFileSync(new URL("../app/privacy/page.tsx", import.meta.url), "utf8");
  assert.match(page, /<AccountDeletion\s*\/>/);
  assert.doesNotMatch(page, /redirect|requireAuth|AuthGuard/);
  assert.match(settings, /href="\/account-deletion"/);
  assert.match(privacy, /href="\/account-deletion"/);
});

test("deletion contact displays only the confirmed international phone number", () => {
  const ui = readFileSync(new URL("../components/account-deletion.tsx", import.meta.url), "utf8");
  const privacy = readFileSync(new URL("../app/privacy/page.tsx", import.meta.url), "utf8");
  for (const source of [ui, privacy]) {
    assert.match(source, /<p(?: className=\{styles\.note\})?><a href="tel:\+864001082026">\+86 4001082026<\/a><\/p>/);
  }
  assert.doesNotMatch(ui, /href="\/support"|Unable to verify your account or resolve an item\?/);
});

test("UI has unchecked consent, separate final confirmation and persists recovery before submission", () => {
  const ui = readFileSync(new URL("../components/account-deletion.tsx", import.meta.url), "utf8");
  const api = readFileSync(new URL("../lib/account-deletion-api.ts", import.meta.url), "utf8");
  assert.match(ui, /\[acknowledged, setAcknowledged\] = useState\(false\)/);
  assert.match(ui, /id="deletion-final-title"/);
  assert.match(ui, /saveDeletionReceipt\(window\.localStorage, saved\)[\s\S]*submitDeletionWithRecovery\(saved\.ticket/);
  assert.match(ui, /const complete = status\?\.status === "completed"/);
  assert.match(ui, /loginHref\("\/account-deletion"\)/);
  assert.match(api, /getAccountDeletionStatus\(ticket: string\)[\s\S]*method: "POST", body: JSON\.stringify\(\{ ticket \}\)/);
  assert.doesNotMatch(ui + api, /console\.|[?&](?:ticket|password)=|localStorage\.clear\(/);
});

test("BFF retains same-origin gate and no-store envelopes before deletion route dispatch", () => {
  const adapter = readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");
  assert.ok(adapter.indexOf("isMutation(request.method) && !sameOrigin(request)") < adapter.indexOf('path.startsWith("canonical/user/account-deletion")'));
  const deletion = adapter.slice(adapter.indexOf('if (path.startsWith("canonical/user/account-deletion"))'), adapter.indexOf('if (path === "health"'));
  assert.match(deletion, /request\.method !== accountDeletionMethods\[operation\]/);
  assert.match(deletion, /request\.nextUrl\.search/);
  assert.match(deletion, /deletionRevokesNormalSession\(result\.body\.data\)[\s\S]*clearAuthCookie/);
  assert.match(deletion, /deletionMayClearSession\(marker, ticket, currentBearer\)\) clearAuthCookie/);
  assert.match(deletion, /httpOnly: true, sameSite: "strict"/);
  assert.doesNotMatch(deletion, /Authorization|publicApiSuccess/);
});
