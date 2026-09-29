import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("Web order adapter follows backend buyer actions and forwards disputes", () => {
  const adapter = fs.readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");
  const api = fs.readFileSync(new URL("../lib/commerce-api.ts", import.meta.url), "utf8");

  assert.match(adapter, /Boolean\(item\.can_confirm\)/);
  assert.match(adapter, /Boolean\(item\.can_cancel\)/);
  assert.match(adapter, /Boolean\(item\.can_dispute\)/);
  assert.match(adapter, /confirm\|complete\|cancel\|dispute\|renew/);
  assert.match(adapter, /action === "dispute"[\s\S]*?reason: text\(body\.reason\)/);
  assert.match(api, /account\/orders\/\$\{id\}\/dispute/);
});

test("Web order workspace exposes backend dispute metadata without a separate fake workflow", () => {
  const workspace = fs.readFileSync(new URL("../components/order-workspace.tsx", import.meta.url), "utf8");
  const legacyPage = fs.readFileSync(new URL("../app/account/disputes/page.tsx", import.meta.url), "utf8");

  assert.match(workspace, /available_actions\.includes\("dispute"\)/);
  assert.match(workspace, /dispute_due_at/);
  assert.match(workspace, /confirmation_due_at/);
  assert.match(workspace, /delivery_due_at/);
  assert.match(workspace, /dispute_reason/);
  assert.match(legacyPage, /redirect\("\/account\/orders"\)/);
  assert.doesNotMatch(legacyPage, /DisputeWorkspace/);
});

test("Web admin resolves disputes through the canonical order ledger", () => {
  const workspace = fs.readFileSync(new URL("../components/admin-dispute-workspace.tsx", import.meta.url), "utf8");
  const api = fs.readFileSync(new URL("../lib/admin-audit-api.ts", import.meta.url), "utf8");
  const legacy = fs.readFileSync(new URL("../lib/internal-api.ts", import.meta.url), "utf8");

  assert.match(workspace, /listAdminOrders\(\{ status: "disputed", page: nextPage, pageSize: DISPUTE_PAGE_SIZE \}\)/);
  assert.match(workspace, /load\(page \+ 1, true\)/);
  assert.match(workspace, /mergeOrders\(current, result\.items\)/);
  assert.match(workspace, /resolveAdminOrderDispute\(selected\.id, \{ action, note \}\)/);
  assert.match(workspace, /退回买家冻结金额/);
  assert.match(workspace, /放行订单资金并继续商家结算/);
  assert.match(workspace, /selected\.ssh_info_present/);
  assert.match(workspace, /selected\?\.ssh_fingerprint/);
  assert.match(workspace, /selected\?\.ssh_info_fingerprint/);
  assert.match(workspace, /selected\?\.product_snapshot/);
  assert.doesNotMatch(workspace, /selected\.ssh_info(?:\W|$)/);
  assert.match(api, /page\?: number; pageSize\?: number/);
  assert.match(api, /page: String\(input\.page \?\? 1\)/);
  assert.match(api, /canonicalApiPath\(`\/orders\/\$\{id\}\/dispute\/resolve`\)/);
  assert.match(api, /action: "refund" \| "release"/);
  assert.doesNotMatch(legacy, /\/api\/v1\/admin\/disputes/);
});
