import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { normalizeAdminReviewPrompt } from "../lib/admin-review-prompt.ts";

test("canceling any admin review prompt prevents submission", () => {
  assert.equal(normalizeAdminReviewPrompt(null, false), null);
  assert.equal(normalizeAdminReviewPrompt(null, true), null);
});

test("required rejection and failure reasons cannot be empty", () => {
  assert.equal(normalizeAdminReviewPrompt("", true), null);
  assert.equal(normalizeAdminReviewPrompt("   ", true), null);
  assert.equal(normalizeAdminReviewPrompt("  资料不符  ", true), "资料不符");
  assert.equal(normalizeAdminReviewPrompt("   ", false), undefined);
});

test("all admin review workspaces guard the prompt before requesting approval or refund", () => {
  const cases = [
    ["../components/admin-withdrawal-workspace.tsx", "kind !== \"approve\"", "approveFinanceWithdrawal(row.id, note)"],
    ["../components/admin-kyc-workspace.tsx", "!approved", "reviewFinanceVerification(row.id, approved, reason)"],
    ["../components/admin-bank-card-workspace.tsx", "!approved", "reviewFinanceBankCard(row.id, approved, reason)"],
    ["../components/admin-refund-workspace.tsx", "false", "initiateAdminRefund(row.id, row.version, note)"],
  ] as const;

  for (const [path, requiredExpression, requestCall] of cases) {
    const source = fs.readFileSync(new URL(path, import.meta.url), "utf8");
    const promptIndex = source.indexOf("normalizeAdminReviewPrompt(window.prompt(");
    const requiredIndex = source.indexOf(requiredExpression, promptIndex);
    const guardIndex = source.indexOf("=== null) return;", requiredIndex);
    const requestIndex = source.indexOf(requestCall, guardIndex);

    assert.ok(promptIndex >= 0, `${path} must normalize the prompt result`);
    assert.ok(requiredIndex > promptIndex, `${path} must require rejection/failure reasons`);
    assert.ok(guardIndex > requiredIndex, `${path} must return when the prompt is canceled or invalid`);
    assert.ok(requestIndex > guardIndex, `${path} must guard before sending the approval request`);
  }
});
