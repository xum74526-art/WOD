import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  adminRechargeActions,
  canResolveUnknownPaymentRefund,
  paymentRefundStatusLabel,
  paymentStatusLabel,
} from "../lib/admin-payment-operations.ts";

test("admin payment actions expose only backend-supported state transitions", () => {
  assert.deepEqual(adminRechargeActions("review", null), { canCredit: true, canRefund: true });
  assert.deepEqual(adminRechargeActions("late_paid_review", null), { canCredit: true, canRefund: true });
  assert.deepEqual(adminRechargeActions("paid", null), { canCredit: false, canRefund: true });
  assert.deepEqual(adminRechargeActions("paid", "unknown"), { canCredit: false, canRefund: false });
  assert.deepEqual(adminRechargeActions("paid", "failed"), { canCredit: false, canRefund: true });
  assert.deepEqual(adminRechargeActions("paid", null, "mapay"), { canCredit: false, canRefund: false });
  assert.deepEqual(adminRechargeActions("review", null, "mapay"), { canCredit: true, canRefund: false });
  assert.deepEqual(adminRechargeActions("refunded", "succeeded"), { canCredit: false, canRefund: false });
  assert.equal(canResolveUnknownPaymentRefund("unknown"), true);
  assert.equal(canResolveUnknownPaymentRefund("submitting"), false);
  assert.equal(canResolveUnknownPaymentRefund("succeeded"), false);
});

test("operator labels distinguish wallet refunds from original-rail CNY refunds", () => {
  assert.equal(paymentStatusLabel("refund_unknown"), "原路退款结果待核验");
  assert.equal(paymentRefundStatusLabel("succeeded"), "原路退款成功");
  const workspace = readFileSync(new URL("../components/admin-payment-operations-workspace.tsx", import.meta.url), "utf8");
  assert.match(workspace, /钱包订单争议退款/);
  assert.match(workspace, /人民币原支付渠道退款/);
  assert.match(workspace, /这不是钱包订单退卡时/);
  assert.match(workspace, /历史 MaPay 商户后台/);
  assert.match(workspace, /对应支付渠道后台/);
  assert.match(workspace, /页面回跳、用户截图和客户端参数都不是成功凭据/);
  assert.match(workspace, /必须由另一名管理员登录七相商户后台/);
});

test("admin payment mutations require confirmation, suppress duplicates, and persist retry ids", () => {
  const workspace = readFileSync(new URL("../components/admin-payment-operations-workspace.tsx", import.meta.url), "utf8");
  const api = readFileSync(new URL("../lib/admin-audit-api.ts", import.meta.url), "utf8");
  const orderMutation = workspace.slice(workspace.indexOf("async function submitOrderAction"), workspace.indexOf("async function submitRefundResolution"));
  const resolution = workspace.slice(workspace.indexOf("async function submitRefundResolution"), workspace.indexOf("const orderActions"));

  assert.ok(orderMutation.indexOf("window.confirm") < orderMutation.indexOf("beginMutation"));
  assert.ok(orderMutation.indexOf("saveClientRequestIntent") < orderMutation.indexOf("reviewAdminRechargeOrder"));
  assert.ok(orderMutation.indexOf("saveClientRequestIntent") < orderMutation.indexOf("createAdminPaymentRefund"));
  assert.ok(orderMutation.indexOf("reviewAdminRechargeOrder") < orderMutation.indexOf("clearClientRequestIntent"));
  assert.match(orderMutation, /orderDetail\.refund\.client_request_id/);
  assert.ok(resolution.indexOf("window.confirm") < resolution.indexOf("beginMutation"));
  assert.match(workspace, /mutationInFlight\.current/);
  assert.match(api, /canonicalApiPath\(`\/admin\/recharge-orders\/\$\{id\}\/review`\)/);
  assert.match(api, /canonicalApiPath\(`\/admin\/recharge-orders\/\$\{id\}\/refunds`\)/);
  assert.match(api, /canonicalApiPath\(`\/admin\/payment-refunds\/\$\{id\}\/resolve`\)/);
});

test("the admin refund route and navigation reach the canonical payment workspace", () => {
  const page = readFileSync(new URL("../app/admin/refunds/page.tsx", import.meta.url), "utf8");
  const navigation = readFileSync(new URL("../components/product-shell.tsx", import.meta.url), "utf8");
  const dashboard = readFileSync(new URL("../components/admin-dashboard.tsx", import.meta.url), "utf8");
  assert.match(page, /AdminPaymentOperationsWorkspace/);
  assert.doesNotMatch(page, /redirect\(/);
  assert.match(navigation, /充值与退款.*\/admin\/refunds/);
  assert.match(dashboard, /充值与人民币退款.*\/admin\/refunds/);
});
