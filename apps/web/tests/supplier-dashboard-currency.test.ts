import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("supplier overview displays revenue through the locale currency formatter", () => {
  const source = fs.readFileSync(new URL("../components/supplier-dashboard.tsx", import.meta.url), "utf8");
  assert.match(source, /formatLedgerMoney\(data\.today_revenue\)/);
  assert.match(source, /formatLedgerMoney\(data\.total_revenue\)/);
  assert.match(source, /\{displayCurrency\}/);
  assert.doesNotMatch(source, /formatFinancialAmount\(data\.(?:today|total)_revenue\)/);
});
