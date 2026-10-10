import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");

test("administrator account controls use the canonical audited backend action", () => {
  const api = read("../lib/admin-audit-api.ts");
  const workspace = read("../components/admin-platform-audit-workspace.tsx");

  assert.match(api, /canonicalApiPath\(`\/admin\/users\/\$\{id\}\/actions`\)/);
  assert.match(api, /"send_password_reset" \| "issue_password_reset_code" \| "freeze" \| "unfreeze" \| "delete"/);
  assert.match(workspace, /管理员看不到原密码、完整邮箱或重置令牌/);
  assert.match(workspace, /旧会话不会恢复/);
  assert.match(workspace, /没有未结订单、资金、退款、提现或争议/);
  assert.match(workspace, /confirm_username/);
  assert.match(workspace, /crypto\.randomUUID\(\)/);
  assert.match(workspace, /重置码只在本次成功响应中显示/);
  assert.match(workspace, /reset_token/);
});

test("user cards expose lifecycle and recovery readiness before enabling actions", () => {
  const workspace = read("../components/admin-platform-audit-workspace.tsx");

  assert.match(workspace, /row\.account_status/);
  assert.match(workspace, /row\.recovery_email_verified/);
  assert.match(workspace, /row\.role !== "admin"/);
  assert.match(workspace, /disabled=\{!row\.recovery_email_verified/);
  assert.match(workspace, /beginUserAction\(row, "issue_password_reset_code"\)/);
  assert.match(workspace, /输入完整用户名确认/);
  assert.match(workspace, /listAdminUserActions/);
  assert.match(workspace, /操作记录/);
  assert.match(workspace, /userTotal > 20/);
});

test("platform self-operated usage orders expose the audited delivery control", () => {
  const api = read("../lib/admin-audit-api.ts");
  const workspace = read("../components/admin-platform-audit-workspace.tsx");

  assert.match(api, /canonicalApiPath\(`\/orders\/\$\{id\}\/deliver`\)/);
  assert.match(api, /ssh_info: sshInfo/);
  assert.match(workspace, /order\.status === "paid"/);
  assert.match(workspace, /order\.purchase_type === "usage"/);
  assert.match(workspace, /order\.seller_type === "kai_self_operated"/);
  assert.match(workspace, /order\.fulfillment_mode === "platform_manual"/);
  assert.match(workspace, /交付 SSH \/ 算力资源/);
  assert.match(workspace, /不要填写密码、私钥、验证码/);
});
