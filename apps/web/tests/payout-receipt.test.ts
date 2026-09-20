import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { canViewPayoutReceipt, PAYOUT_RECEIPT_ACCEPT, PAYOUT_RECEIPT_HELP_TEXT } from "../lib/payout-receipt.ts";

test("payout receipt picker matches the backend JPG, PNG, and PDF contract", () => {
  assert.equal(PAYOUT_RECEIPT_ACCEPT, "image/jpeg,image/png,application/pdf");
  assert.doesNotMatch(PAYOUT_RECEIPT_ACCEPT, /webp/i);
  assert.equal(PAYOUT_RECEIPT_HELP_TEXT, "支持 JPG、PNG、PDF，最大 5MB");
  assert.doesNotMatch(PAYOUT_RECEIPT_HELP_TEXT, /webp/i);
});

test("admin payout form uses the shared receipt contract", () => {
  const workspace = fs.readFileSync(new URL("../components/admin-withdrawal-workspace.tsx", import.meta.url), "utf8");

  assert.match(workspace, /accept=\{PAYOUT_RECEIPT_ACCEPT\}/);
  assert.match(workspace, /<small>\{PAYOUT_RECEIPT_HELP_TEXT\}<\/small>/);
  assert.doesNotMatch(workspace, /image\/webp/);
});

test("receipt link is available only for paid withdrawals with stored evidence", () => {
  assert.equal(canViewPayoutReceipt({ status: "paid", receipt_available: true }), true);
  assert.equal(canViewPayoutReceipt({ status: "paid", receipt_available: false }), false);
  assert.equal(canViewPayoutReceipt({ status: "manual_payment_pending", receipt_available: true }), false);

  const workspace = fs.readFileSync(new URL("../components/admin-withdrawal-workspace.tsx", import.meta.url), "utf8");
  const financeApi = fs.readFileSync(new URL("../lib/mobile-finance-api.ts", import.meta.url), "utf8");
  assert.match(workspace, /canViewPayoutReceipt\(row\) && <div className="finance-photo-links">/);
  assert.match(workspace, /href=\{financeWithdrawalReceipt\(row\.id\)\} target="_blank" rel="noreferrer">下载打款凭证<\/a>/);
  assert.match(financeApi, /receipt_available: boolean/);
  assert.match(financeApi, /path\(`\/finance\/withdrawals\/\$\{id\}\/receipt`\)/);
  assert.doesNotMatch(workspace, /API_ORIGIN|wod\.kai\.com\/api\/finance\/withdrawals/);
});
