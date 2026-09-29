import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

function read(path: string) {
  return fs.readFileSync(new URL(path, import.meta.url), "utf8");
}

test("user notification center exposes viewed and account-scoped delete actions", () => {
  const api = read("../lib/internal-api.ts");
  const workspace = read("../components/notification-workspace.tsx");
  const adapter = read("../lib/api-adapter.ts");

  assert.match(api, /deleteNotification\(id: number\)/);
  assert.match(api, /method: "DELETE"/);
  assert.match(workspace, /deleteNotification\(row\.id\)/);
  assert.match(workspace, /标为已查看/);
  assert.match(workspace, /全部标为已查看/);
  assert.match(adapter, /expires_at: text\(item\.expires_at\) \|\| null/);
  assert.match(adapter, /amount_cny: text\(item\.amount_cny\) \|\| null/);
  assert.match(workspace, /localizedNotificationBody\(row, locale, displayCurrencyConfig, displayCurrency\)/);
});

test("administrator announcements expose expiration and auditable revoke", () => {
  const api = read("../lib/admin-audit-api.ts");
  const workspace = read("../components/admin-notification-workspace.tsx");

  assert.match(api, /expires_at\?: string \| null/);
  assert.match(api, /revokeAdminNotificationBroadcast/);
  assert.match(api, /notification-broadcasts\/\$\{id\}\/revoke/);
  assert.match(workspace, /type="datetime-local"/);
  assert.match(workspace, /localDateTimeInputToUtcIso\(form\.expires_at\)/);
  assert.match(workspace, /revokeAdminNotificationBroadcast\(row\.id, reason\)/);
  assert.match(workspace, /row\.status === "completed"/);
});
