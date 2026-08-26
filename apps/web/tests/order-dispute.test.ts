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
