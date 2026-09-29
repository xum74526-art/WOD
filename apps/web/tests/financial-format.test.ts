import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { financialDecimal, formatFinancialAmount } from "../lib/financial-format.ts";
import {
  convertCardHoursToDisplay,
  convertDisplayToCardHours,
  displayCurrencyForLocale,
  formatCardHoursForLocale,
  formatCnyForLocale,
  formatCnySettlement,
  normalizeDisplayInputToCny,
} from "../lib/display-currency.ts";
import { localizeSupplierName } from "../lib/market-localization.ts";

test("financial values use exactly three decimal places", () => {
  assert.equal(formatFinancialAmount(1.002, "en-US"), "1.002");
  assert.equal(formatFinancialAmount(0.00998, "en-US"), "0.010");
  assert.equal(formatFinancialAmount(12, "en-US"), "12.000");
  assert.equal(formatFinancialAmount(1234.5678, "en-US"), "1,234.568");
  assert.equal(formatFinancialAmount(Number.NaN, "en-US"), "0.000");
  assert.equal(financialDecimal(19.898521), "19.899");
});

test("language supplies only the initial currency while an explicit display currency applies the dated rate", () => {
  const config = {
    base_currency: "CNY" as const,
    settlement_currency: "CNY" as const,
    fraction_digits: 3 as const,
    card_hour_cny_rate: 1,
    rates: { CNY: 1, HKD: 1.08, USD: 0.14 },
    rate_mode: "daily_reference" as const,
    rate_source: "TEST",
    rate_date: "2026-09-28",
    rates_stale: false,
    conversion_scope: "display_only" as const,
  };

  assert.equal(displayCurrencyForLocale("zh-Hans"), "CNY");
  assert.equal(displayCurrencyForLocale("zh-Hant"), "HKD");
  assert.equal(displayCurrencyForLocale("en"), "USD");
  assert.equal(formatCardHoursForLocale(1, "zh-Hans", config), "¥1.000");
  assert.equal(formatCardHoursForLocale(1, "zh-Hant", config), "HK$1.080");
  assert.equal(formatCardHoursForLocale(1, "en", config), "US$0.140");
  assert.equal(formatCnyForLocale(10, "en", config), "US$1.400");
  assert.equal(formatCnyForLocale(100, "zh-Hant", config), "HK$108.000");
  assert.equal(formatCnyForLocale(100, "en", config), "US$14.000");
  assert.equal(formatCnyForLocale(100, "en", config, "HKD"), "HK$108.000");
  assert.equal(formatCnyForLocale(100, "zh-Hant", config, "CNY"), "¥100.000");
  assert.equal(formatCnySettlement(100), "¥100.000");
  assert.equal(convertCardHoursToDisplay(10, "zh-Hans", config), 10);
  assert.ok(Math.abs(convertDisplayToCardHours(1.4, "en", config) - 10) < 1e-9);
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

test("three-decimal display input preserves legal CNY payment boundaries", () => {
  const config = {
    base_currency: "CNY" as const,
    settlement_currency: "CNY" as const,
    fraction_digits: 3 as const,
    card_hour_cny_rate: 1,
    rates: { CNY: 1, HKD: 1.169032900251, USD: 0.149020326907 },
    rate_mode: "daily_reference" as const,
    rate_source: "TEST",
    rate_date: "2026-09-29",
    rates_stale: false,
    conversion_scope: "display_only" as const,
  };
  assert.equal(normalizeDisplayInputToCny("1.490", "en", config, { fractionDigits: 2, minimum: 10 }), 10);
  assert.equal(normalizeDisplayInputToCny("1.490", "en", config, { fractionDigits: 3, minimum: 10 }), 10);
  assert.equal(normalizeDisplayInputToCny("1.489", "en", config, { fractionDigits: 3, minimum: 10 }), 9.992);
});

test("English market copy does not render Chinese backend assurance fields", () => {
  const market = fs.readFileSync(new URL("../components/merchant-resource-market.tsx", import.meta.url), "utf8");
  const locale = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

  assert.doesNotMatch(market, /row\.assurance_(?:label|description)/);
  assert.match(market, /t\("market\.assurance\.kai"/);
  assert.match(market, /t\("market\.assurance\.merchantDirect"/);
  assert.match(market, /formatCardHoursForLocale\(row\.unit_price_ch, locale, capabilities\.display_currency, displayCurrency\)/);
  assert.match(locale, /"market\.buy": "Buy Now"/);
  assert.match(locale, /"market\.hourly": "Hourly price"/);
  assert.equal(localizeSupplierName("KAI 自营", "en"), "KAI Self-operated");
});
