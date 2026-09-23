import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  canPrepareRechargeRestart,
  isRegisteredBankCardStatus,
  luhnCheckCardNumber,
  minimumRechargeAmountCny,
  minimumWithdrawalCardHours,
  rechargeBlocksNewOrder,
  rechargeMatchesActiveOrder,
  rechargeCanCancel,
  rechargeCanPay,
  rechargeCanQuery,
  rechargeCanRestart,
  rechargeUiLabel,
  rechargeUiState,
} from "../lib/finance-ui.ts";

test("recharge and withdrawal never fall below the production minimums", () => {
  assert.equal(minimumRechargeAmountCny(), 10);
  assert.equal(minimumRechargeAmountCny(0.01), 10);
  assert.equal(minimumRechargeAmountCny(20), 20);
  assert.equal(minimumWithdrawalCardHours(), 10);
  assert.equal(minimumWithdrawalCardHours(0.01), 10);
  assert.equal(minimumWithdrawalCardHours(25), 25);
});

test("recharge only succeeds after the backend has credited card hours", () => {
  assert.equal(rechargeUiState({ status: "paid" }), "processing");
  assert.equal(rechargeUiState({ status: "review" }), "processing");
  assert.equal(rechargeUiState({ status: "late_paid_review" }), "processing");
  assert.equal(rechargeUiState({ status: "paid", credited_at: "2026-08-24T01:00:00" }), "success");
  assert.equal(rechargeBlocksNewOrder({ status: "paid" }), true);
  assert.equal(rechargeBlocksNewOrder(null), false);
});

test("only the same active amount and payment channel are treated as a duplicate", () => {
  const active = { status: "pending", amount_cny: "100.00", channel: "alipay" };
  assert.equal(rechargeMatchesActiveOrder(active, 100, "alipay"), true);
  assert.equal(rechargeMatchesActiveOrder(active, 50, "alipay"), false);
  assert.equal(rechargeMatchesActiveOrder(active, 100, "wxpay"), false);
  assert.equal(rechargeMatchesActiveOrder({ ...active, status: "failed" }, 100, "alipay"), false);
});

test("refund states take precedence over credited_at and never render as recharge success", () => {
  const creditedAt = "2026-08-24T01:00:00";
  const cases = [
    ["refund_pending", "退款提交中"],
    ["refund_unknown", "结果待核验"],
    ["refunded", "已退款"],
  ] as const;

  for (const [status, label] of cases) {
    const order = { status, credited_at: creditedAt };
    assert.equal(rechargeUiState(order), status);
    assert.notEqual(rechargeUiState(order), "success");
    assert.equal(rechargeUiLabel(order), label);
  }
});

test("recharge actions require an explicit backend capability", () => {
  assert.equal(rechargeCanPay({ status: "pending" }), false);
  assert.equal(rechargeCanPay({ status: "pending", can_pay: true }), true);
  assert.equal(rechargeCanPay({ status: "refunded", credited_at: "2026-08-24T01:00:00", can_pay: true }), false);
  assert.equal(rechargeCanQuery({ status: "pending" }), false);
  assert.equal(rechargeCanQuery({ status: "pending", can_query: true }), true);
  assert.equal(rechargeCanCancel({ status: "pending" }), false);
  assert.equal(rechargeCanCancel({ status: "pending", can_cancel: true }), true);
});

test("credited refund states reject money actions even when backend flags are inconsistent", () => {
  for (const status of ["refund_pending", "refund_unknown", "refunded"] as const) {
    const order = {
      status,
      credited_at: "2026-08-24T01:00:00",
      can_pay: true,
      can_query: true,
      can_cancel: true,
    };
    assert.equal(rechargeCanPay(order), false);
    assert.equal(rechargeCanQuery(order), false);
    assert.equal(rechargeCanCancel(order), false);
    assert.equal(rechargeCanRestart(order), false);
  }
});

test("wallet buttons use the defensive capability helpers instead of raw flags", () => {
  const workspace = readFileSync(new URL("../components/payment-workspace.tsx", import.meta.url), "utf8");
  assert.match(workspace, /rechargeCanPay\(pendingPayment\)/);
  assert.match(workspace, /rechargeCanQuery\(pendingPayment\)/);
  assert.match(workspace, /rechargeCanCancel\(pendingPayment\)/);
  assert.match(workspace, /rechargeCanQuery\(row\)/);
  assert.match(workspace, /rechargeCanCancel\(row\)/);
  assert.match(workspace, /rechargeMatchesActiveOrder\(pendingPayment, normalizedValue, recharge\.payment_type\)/);
  assert.doesNotMatch(workspace, /can_query !== false|can_pay !== false/);
  assert.match(workspace, /rechargeEntryEnabled && rechargeCanRestart\(pendingPayment\) && <button/);
});

test("only terminal failed recharge orders can restart", () => {
  assert.equal(rechargeCanRestart({ status: "failed" }), true);
  assert.equal(rechargeCanRestart({ status: "expired" }), true);
  assert.equal(rechargeCanRestart({ status: "canceled" }), true);
  assert.equal(rechargeCanRestart({ status: "pending" }), false);
  assert.equal(rechargeCanRestart({ status: "paid" }), false);
});

test("restarting history never overwrites a different active recovery session", () => {
  assert.equal(canPrepareRechargeRestart({ order_no: "OLD", status: "failed" }, "OLD", "OLD"), true);
  assert.equal(canPrepareRechargeRestart({ order_no: "LIVE", status: "pending" }, "LIVE", "OLD"), false);
  assert.equal(canPrepareRechargeRestart(null, "LIVE", "OLD"), false);
  assert.equal(canPrepareRechargeRestart({ order_no: "LIVE", status: "paid" }, "", "OLD"), false);
});

test("bank card eligibility and Luhn checks match the apps", () => {
  assert.equal(isRegisteredBankCardStatus("registered"), true);
  assert.equal(isRegisteredBankCardStatus("pending_review"), true);
  assert.equal(isRegisteredBankCardStatus("active"), true);
  assert.equal(isRegisteredBankCardStatus("rejected"), false);
  assert.equal(luhnCheckCardNumber("4111111111111111"), true);
  assert.equal(luhnCheckCardNumber("4111111111111112"), false);
  assert.equal(luhnCheckCardNumber("123"), false);
});
