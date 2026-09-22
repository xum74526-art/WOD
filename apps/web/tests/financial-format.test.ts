import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { financialDecimal, formatFinancialAmount } from "../lib/financial-format.ts";
import { localizeSupplierName } from "../lib/market-localization.ts";

test("financial values use exactly three decimal places", () => {
  assert.equal(formatFinancialAmount(1.002, "en-US"), "1.002");
  assert.equal(formatFinancialAmount(0.00998, "en-US"), "0.010");
  assert.equal(formatFinancialAmount(12, "en-US"), "12.000");
  assert.equal(formatFinancialAmount(1234.5678, "en-US"), "1,234.568");
  assert.equal(formatFinancialAmount(Number.NaN, "en-US"), "0.000");
  assert.equal(financialDecimal(19.898521), "19.899");
});

test("Web, Android and iOS share the three-decimal display contract", () => {
  const androidFormat = fs.readFileSync(new URL("../../android/src/utils/format.ts", import.meta.url), "utf8");
  const iosFormat = fs.readFileSync(new URL("../../ios/src/utils/format.ts", import.meta.url), "utf8");
  const androidAmount = fs.readFileSync(new URL("../../android/src/components/AmountText.vue", import.meta.url), "utf8");
  const iosAmount = fs.readFileSync(new URL("../../ios/src/components/AmountText.vue", import.meta.url), "utf8");

  for (const source of [androidFormat, iosFormat]) {
    assert.match(source, /minimumFractionDigits: 3/);
    assert.match(source, /maximumFractionDigits: 3/);
    assert.match(source, /export function formatAmount/);
  }
  for (const source of [androidAmount, iosAmount]) {
    assert.match(source, /minimumFractionDigits: 3/);
    assert.match(source, /maximumFractionDigits: 3/);
  }
});

test("English market copy does not render Chinese backend assurance fields", () => {
  const market = fs.readFileSync(new URL("../components/merchant-resource-market.tsx", import.meta.url), "utf8");
  const locale = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

  assert.doesNotMatch(market, /row\.assurance_(?:label|description)/);
  assert.match(market, /t\("market\.assurance\.kai"/);
  assert.match(market, /t\("market\.assurance\.merchantDirect"/);
  assert.match(market, /formatFinancialAmount\(row\.unit_price_ch/);
  assert.match(locale, /"market\.buy": "Buy Now"/);
  assert.match(locale, /"market\.hourly": "Hourly price"/);
  assert.equal(localizeSupplierName("KAI 自营", "en"), "KAI Self-operated");
});
