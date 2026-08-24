import assert from "node:assert/strict";
import test from "node:test";
import {
  canPrepareRechargeRestart,
  isRegisteredBankCardStatus,
  luhnCheckCardNumber,
  rechargeBlocksNewOrder,
  rechargeCanRestart,
  rechargeUiState,
} from "../lib/finance-ui.ts";

test("recharge only succeeds after the backend has credited card hours", () => {
  assert.equal(rechargeUiState({ status: "paid" }), "processing");
  assert.equal(rechargeUiState({ status: "review" }), "processing");
  assert.equal(rechargeUiState({ status: "late_paid_review" }), "processing");
  assert.equal(rechargeUiState({ status: "paid", credited_at: "2026-08-24T01:00:00" }), "success");
  assert.equal(rechargeBlocksNewOrder({ status: "paid" }), true);
  assert.equal(rechargeBlocksNewOrder(null), false);
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
