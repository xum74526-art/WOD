import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { hourlyOrderBody, kaiPricingQuery, webRequestId } from "../lib/web-business-contract.ts";

test("all live market requests force KAI Pricing as the only source", () => {
  const query = new URLSearchParams(kaiPricingQuery({ model: "H100", variant: "80GB", sources: "vast,autodl" }));
  assert.equal(query.get("sources"), "kai");
  assert.equal(query.get("model"), "H100");
});

test("new and renewal orders use integer hours plus a Web request id", () => {
  const requestId = webRequestId("order", "12345678-1234-1234-1234-123456789abc");
  assert.deepEqual(hourlyOrderBody(24, requestId), { hours: 24, client_request_id: requestId });
  assert.equal("cycle_days" in hourlyOrderBody(24, requestId), false);
  assert.throws(() => hourlyOrderBody(1.5, requestId), /整数小时/);
  assert.throws(() => hourlyOrderBody(721, requestId), /1 至 720/);
});

test("released Web account copy does not expose retired test-only wording", () => {
  const source = fs.readFileSync(new URL("../components/mobile-account-services.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(
    source,
    /封闭测试|闭测|功能测试|功能验证|历史测试|测试版|测试奖励|测试收益|测试卡片|测试交易|closed[- ]test|functional[- ]validation|historical test|test build|test reward|test return|test card|test transaction/i,
  );
});

test("Web market summary and chart use the canonical KAI candle contract", () => {
  const adapter = fs.readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");
  const panel = fs.readFileSync(new URL("../components/live-market-panel.tsx", import.meta.url), "utf8");
  const summary = adapter.slice(
    adapter.indexOf("async function marketSummary"),
    adapter.indexOf("async function accountSummary"),
  );

  assert.match(summary, /\/api\/market\/prices\/candles/);
  assert.match(summary, /sources:\s*"kai"/);
  assert.match(summary, /close_price_card_hours/);
  assert.match(summary, /median_price_card_hours/);
  assert.doesNotMatch(summary, /\/api\/market\/prices\/history/);
  assert.match(panel, /`\$\{item\.gpu_model\} \$\{item\.gpu_variant\}`/);
  assert.match(panel, /open_price_card_hours/);
  assert.match(panel, /median_price_card_hours/);
});

test("Web compute catalogue shows one representative per GPU identity in card hours", () => {
  const adapter = fs.readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");
  const market = fs.readFileSync(new URL("../components/merchant-resource-market.tsx", import.meta.url), "utf8");
  const detail = fs.readFileSync(new URL("../components/product-detail.tsx", import.meta.url), "utf8");

  assert.match(adapter, /query\.set\("page_size", "100"\)/);
  assert.match(adapter, /query\.set\("market_source", "kai"\)/);
  assert.match(adapter, /query\.set\("representative", "true"\)/);
  assert.match(market, /row\.unit_price_ch/);
  assert.match(market, /卡时 \/ GPU·小时/);
  assert.match(detail, /product\.unit_price_ch/);
  assert.match(detail, /卡时 \/ GPU·小时/);
  assert.doesNotMatch(detail, /KAI 行情估值|¥|product\.price\.amount/);
  const serverData = fs.readFileSync(new URL("../lib/server/public-page-data.ts", import.meta.url), "utf8");
  assert.match(serverData, /\/api\/products\?page=1&page_size=100&market_source=kai&representative=true/);
});

test("Web market chart and pulse consistently render KAI prices in card hours", () => {
  const chart = fs.readFileSync(new URL("../components/gpu-candlestick-chart.tsx", import.meta.url), "utf8");
  const pulse = fs.readFileSync(new URL("../components/market-pulse-rail.tsx", import.meta.url), "utf8");

  for (const source of [chart, pulse]) {
    assert.match(source, /median_price_card_hours/);
    assert.match(source, /卡时 \/ GPU·小时/);
    assert.doesNotMatch(source, /median_price_cny/);
    assert.doesNotMatch(source, /CNY \/ GPU·h/);
  }
  assert.match(chart, /close_price_card_hours/);
  assert.doesNotMatch(chart, /close_price_cny/);
});
