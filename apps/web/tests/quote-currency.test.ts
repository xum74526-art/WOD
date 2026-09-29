import assert from "node:assert/strict";
import test from "node:test";
import {
  displayInputToQuoteAmount,
  formatQuoteAmountForLocale,
  quoteAmountToDisplayInput,
} from "../lib/quote-currency.ts";

const config = {
  base_currency: "CNY" as const,
  settlement_currency: "CNY" as const,
  fraction_digits: 3 as const,
  card_hour_cny_rate: 1,
  rates: { CNY: 1, HKD: 1.08, USD: 0.14 },
  rate_mode: "daily_reference" as const,
  rate_source: "TEST",
  rate_date: "2026-09-29",
  rates_stale: false,
  conversion_scope: "display_only" as const,
};

test("quote display follows locale currency while storage remains CNY", () => {
  assert.equal(formatQuoteAmountForLocale(100, "CNY", "zh-Hans", config), "¥100.000");
  assert.equal(formatQuoteAmountForLocale(100, "CNY", "zh-Hant", config), "HK$108.000");
  assert.equal(formatQuoteAmountForLocale(100, "CNY", "en", config), "US$14.000");
  assert.equal(quoteAmountToDisplayInput(100, "CNY", "en", config), "14.000");
  assert.equal(displayInputToQuoteAmount(14, "CNY", "en", config), 100);
});

test("legacy ledger quotes and unknown currencies stay deterministic", () => {
  assert.equal(formatQuoteAmountForLocale(25, "CH", "zh-Hant", config), "HK$27.000");
  assert.equal(displayInputToQuoteAmount(27, "CH", "zh-Hant", config), 25);
  assert.equal(formatQuoteAmountForLocale(9.5, "USDT", "en", config), "9.500 USDT");
  assert.equal(displayInputToQuoteAmount(9.5, "USDT", "en", config), 9.5);
});
