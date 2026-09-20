import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { rechargeCanRequestRefund, rechargeRefundRequestLabel } from "../lib/finance-ui.ts";

const api = readFileSync(new URL("../lib/mobile-business-api.ts", import.meta.url), "utf8");
const workspace = readFileSync(new URL("../components/payment-workspace.tsx", import.meta.url), "utf8");

test("only owned Qixiang payments in a refundable server state expose the request action", () => {
  assert.equal(rechargeCanRequestRefund({ provider: "qixiangpay", status: "paid", credited_at: "2026-09-20T00:00:00" }), true);
  assert.equal(rechargeCanRequestRefund({ provider: "qixiangpay", status: "review" }), true);
  assert.equal(rechargeCanRequestRefund({ provider: "qixiangpay", status: "late_paid_review" }), true);
  assert.equal(rechargeCanRequestRefund({ provider: "qixiangpay", status: "paid" }), false);
  assert.equal(rechargeCanRequestRefund({ provider: "mapay", status: "paid", credited_at: "2026-09-20T00:00:00" }), false);
  assert.equal(rechargeCanRequestRefund({ provider: "qixiangpay", status: "refunded", credited_at: "2026-09-20T00:00:00" }), false);
});

test("refund request labels distinguish review, processing and final outcomes", () => {
  assert.equal(rechargeRefundRequestLabel({ status: "pending_review" }), "待平台审核");
  assert.equal(rechargeRefundRequestLabel({ status: "processing" }), "退款处理中");
  assert.equal(rechargeRefundRequestLabel({ status: "succeeded" }), "退款已完成");
  assert.equal(rechargeRefundRequestLabel({ status: "rejected" }), "申请已驳回");
});

test("Web submits an idempotent refund application and shows its server status history", () => {
  assert.match(api, /orders\/\$\{encodeURIComponent\(orderNo\)\}\/refund-requests/);
  assert.match(api, /payments\/qixiang\/refund-requests\?\$\{query\.toString\(\)\}/);
  assert.match(workspace, /REFUND_REQUEST_INTENT_KEY_PREFIX/);
  assert.match(workspace, /saveClientRequestIntent\(storage, intentKey, intent\)/);
  assert.match(workspace, /createRechargeRefundRequest\(refundFormOrder\.order_no/);
  assert.match(workspace, /setTab\("refundRequests"\)/);
  assert.match(workspace, /rechargeRefundRequestLabel\(row\)/);
  assert.match(workspace, /审核通过后才会发起原路退款/);
});
