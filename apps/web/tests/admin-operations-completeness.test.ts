import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function source(relative: string) {
  return readFileSync(new URL(`../${relative}`, import.meta.url), "utf8");
}

test("administrator navigation exposes support, moderation, and audit operations", () => {
  const shell = source("components/product-shell.tsx");
  const dashboard = source("components/admin-dashboard.tsx");
  for (const route of ["/admin/support", "/admin/moderation", "/admin/audit"]) {
    assert.match(shell, new RegExp(route.replaceAll("/", "\\/")));
    assert.match(dashboard, new RegExp(route.replaceAll("/", "\\/")));
  }
  assert.match(dashboard, /getAdminOverview\(\)/);
  assert.match(dashboard, /work_queues/);
});

test("human support is a real audited administrator workflow", () => {
  const workspace = source("components/admin-support-workspace.tsx");
  const client = source("lib/admin-audit-api.ts");
  for (const action of ["claim", "assign", "reply", "resolve", "close", "reopen"]) {
    assert.match(workspace, new RegExp(`\\"${action}\\"`));
  }
  assert.match(client, /\/admin\/support-tickets\/\$\{id\}\/actions/);
  assert.match(workspace, /AdminQueuePagination/);
});

test("merchant controls suspend sales and require per-product relisting", () => {
  const review = source("components/supplier-review.tsx");
  const client = source("lib/admin-audit-api.ts");
  assert.match(review, /manageAdminSupplierStatus/);
  assert.match(review, /manageAdminSupplierProduct/);
  assert.match(review, /selected\.status === "suspended"/);
  assert.match(client, /\/supplier\/admin\/suppliers\/\$\{id\}\/status/);
  assert.match(client, /\/supplier\/admin\/products\/\$\{id\}\/status/);
});

test("previously truncated administrator lists use total-aware pagination", () => {
  for (const file of [
    "components/admin-buy-request-workspace.tsx",
    "components/admin-notification-workspace.tsx",
    "components/comment-moderation.tsx",
    "components/admin-platform-audit-workspace.tsx",
  ]) {
    const value = source(file);
    assert.match(value, /AdminQueuePagination/, file);
    assert.doesNotMatch(value, /pageSize:\s*100/, file);
  }
});

test("administrator audit log is filterable and paginated", () => {
  const workspace = source("components/admin-audit-log-workspace.tsx");
  const client = source("lib/admin-audit-api.ts");
  assert.match(workspace, /actorUserId/);
  assert.match(workspace, /objectType/);
  assert.match(workspace, /AdminQueuePagination/);
  assert.match(client, /\/finance\/audit-logs/);
});
