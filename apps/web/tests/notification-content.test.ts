import assert from "node:assert/strict";
import test from "node:test";
import { localizedNotificationBody } from "../lib/notification-content.ts";

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

const revenue = {
  body: "今日已记录人民币 ¥100.000 收益，可在收益中心查看明细。",
  body_en: "CNY ¥100.000 of revenue has been recorded today.",
  template_key: "daily_revenue_recorded",
  amount_cny: "100.000",
};

test("structured revenue notification converts its canonical CNY amount", () => {
  assert.match(localizedNotificationBody(revenue, "zh-Hans", config), /¥100\.000/);
  assert.match(localizedNotificationBody(revenue, "zh-Hant", config), /HK\$108\.000/);
  assert.match(localizedNotificationBody(revenue, "en", config), /US\$14\.000/);
});

test("ordinary notification copy remains unchanged except Traditional conversion", () => {
  const ordinary = { body: "通知设置已更新。", body_en: "Settings updated.", template_key: null, amount_cny: null };
  assert.equal(localizedNotificationBody(ordinary, "en", config), "Settings updated.");
  assert.equal(localizedNotificationBody(ordinary, "zh-Hant", config), "通知設置已更新。");
});
