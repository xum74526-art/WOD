import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  adminRechargeActions,
  canReviewPaymentRefundRequest,
  canResolveUnknownPaymentRefund,
  paymentRefundRequestStatusLabel,
  paymentRefundStatusLabel,
  paymentStatusLabel,
} from "../lib/admin-payment-operations.ts";

test("admin payment actions expose only backend-supported state transitions", () => {
  assert.deepEqual(adminRechargeActions("review", null), { canCredit: true, canRefund: true });
  assert.deepEqual(adminRechargeActions("late_paid_review", null), { canCredit: true, canRefund: true });
  assert.deepEqual(adminRechargeActions("paid", null), { canCredit: false, canRefund: true });
  assert.deepEqual(adminRechargeActions("paid", null, "qixiangpay", "pending_review"), { canCredit: false, canRefund: false });
  assert.deepEqual(adminRechargeActions("paid", null, "qixiangpay", "processing"), { canCredit: false, canRefund: false });
  assert.deepEqual(adminRechargeActions("paid", null, "qixiangpay", "rejected"), { canCredit: false, canRefund: true });
  assert.deepEqual(adminRechargeActions("paid", "unknown"), { canCredit: false, canRefund: false });
  assert.deepEqual(adminRechargeActions("paid", "failed"), { canCredit: false, canRefund: true });
  assert.deepEqual(adminRechargeActions("paid", null, "mapay"), { canCredit: false, canRefund: false });
  assert.deepEqual(adminRechargeActions("review", null, "mapay"), { canCredit: true, canRefund: false });
  assert.deepEqual(adminRechargeActions("refunded", "succeeded"), { canCredit: false, canRefund: false });
  assert.equal(canResolveUnknownPaymentRefund("unknown"), true);
  assert.equal(canResolveUnknownPaymentRefund("submitting"), false);
  assert.equal(canResolveUnknownPaymentRefund("succeeded"), false);
  assert.equal(canReviewPaymentRefundRequest("pending_review"), true);
  assert.equal(canReviewPaymentRefundRequest("processing"), false);
  assert.equal(canReviewPaymentRefundRequest("rejected"), false);
});

test("operator labels distinguish wallet refunds from original-rail CNY refunds", () => {
  assert.equal(paymentStatusLabel("refund_unknown"), "原路退款结果待核验");
  assert.equal(paymentRefundStatusLabel("succeeded"), "原路退款成功");
  assert.equal(paymentRefundRequestStatusLabel("pending_review"), "待审核");
  assert.equal(paymentRefundRequestStatusLabel("processing"), "退款处理中");
  const workspace = readFileSync(new URL("../components/admin-payment-operations-workspace.tsx", import.meta.url), "utf8");
  assert.match(workspace, /钱包订单争议退款/);
  assert.match(workspace, /人民币原支付渠道退款/);
  assert.match(workspace, /这不是钱包订单余额退款/);
  assert.match(workspace, /历史 MaPay 商户后台/);
  assert.match(workspace, /对应支付渠道后台/);
  assert.match(workspace, /页面回跳、用户截图和客户端参数都不是成功凭据/);
  assert.match(workspace, /必须由另一名管理员登录七相商户后台/);
  assert.match(workspace, /批准不等于渠道已退款成功/);
  assert.match(workspace, /驳回只记录审核结论，不退款，也不扣减用户账户金额/);
  assert.match(workspace, /formatFinancialAmount\(value\)/);
  assert.match(workspace, /<dt>充值金额<\/dt>/);
  assert.match(workspace, /<dt>原路退款金额<\/dt>/);
  assert.doesNotMatch(workspace, /渠道付款 \/ 账户入账|渠道退款 \/ 对应账户金额/);
  assert.doesNotMatch(workspace, /toFixed\(6\)/);
});

test("admin payment mutations require confirmation, suppress duplicates, and persist retry ids", () => {
  const workspace = readFileSync(new URL("../components/admin-payment-operations-workspace.tsx", import.meta.url), "utf8");
  const api = readFileSync(new URL("../lib/admin-audit-api.ts", import.meta.url), "utf8");
  const orderMutation = workspace.slice(workspace.indexOf("async function submitOrderAction"), workspace.indexOf("async function submitRefundResolution"));
  const resolution = workspace.slice(workspace.indexOf("async function submitRefundResolution"), workspace.indexOf("const orderActions"));
  const requestReview = workspace.slice(workspace.indexOf("async function submitRefundRequestReview"), workspace.indexOf("async function submitRefundResolution"));

  assert.ok(orderMutation.indexOf("window.confirm") < orderMutation.indexOf("beginMutation"));
  assert.ok(orderMutation.indexOf("saveClientRequestIntent") < orderMutation.indexOf("reviewAdminRechargeOrder"));
  assert.ok(orderMutation.indexOf("saveClientRequestIntent") < orderMutation.indexOf("createAdminPaymentRefund"));
  assert.ok(orderMutation.indexOf("reviewAdminRechargeOrder") < orderMutation.indexOf("clearClientRequestIntent"));
  assert.match(orderMutation, /orderDetail\.refund\.client_request_id/);
  assert.ok(resolution.indexOf("window.confirm") < resolution.indexOf("beginMutation"));
  assert.ok(requestReview.indexOf("window.confirm") < requestReview.indexOf("beginMutation"));
  assert.match(requestReview, /reviewAdminPaymentRefundRequest/);
  assert.match(workspace, /mutationInFlight\.current/);
  assert.match(api, /canonicalApiPath\(`\/admin\/recharge-orders\/\$\{id\}\/review`\)/);
  assert.match(api, /canonicalApiPath\(`\/admin\/recharge-orders\/\$\{id\}\/refunds`\)/);
  assert.match(api, /canonicalApiPath\(`\/admin\/payment-refunds\/\$\{id\}\/resolve`\)/);
  assert.match(api, /canonicalApiPath\(`\/admin\/payment-refund-requests\$\{query\(input\)\}`\)/);
  assert.match(api, /canonicalApiPath\(`\/admin\/payment-refund-requests\/\$\{id\}`\)/);
  assert.match(api, /canonicalApiPath\(`\/admin\/payment-refund-requests\/\$\{id\}\/review`\)/);
  assert.match(workspace, /用户退款申请/);
  assert.match(workspace, /refund_request\?\.status/);
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
