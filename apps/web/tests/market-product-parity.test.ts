import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { fallbackWebProductImage, resolveWebProductImage } from "../lib/product-image.ts";
import { clampPurchaseHours, estimateProductExpiryRebate, type ProductRebateSummary } from "../lib/product-purchase.ts";
import { localizeMarketRegion } from "../lib/market-localization.ts";

const rewardSummary: ProductRebateSummary = {
  month_spent: 100,
  month_rebated: 10,
  current_rate: 5,
  next_tier_hint: "",
  pending_rebate: 0,
  monthly_cap: 500,
  rewards_enabled: true,
  reward_mode: "live",
  minimum_order_amount: 0,
  tiers: [{ max_month_spent: null, rate: 5 }],
};

test("Web product images safely honor image_url and give B300 a real fallback", () => {
  assert.equal(fallbackWebProductImage("B300 288GB"), "/images/h100.jpg");
  assert.equal(resolveWebProductImage("/static/gpu/gpu.png", "B300"), "/images/h100.jpg");
  assert.equal(resolveWebProductImage("/uploads/unreachable.jpg", "B300"), "/images/h100.jpg");
  assert.equal(resolveWebProductImage("https://cdn.example.com/gpu.webp", "A100"), "https://cdn.example.com/gpu.webp");
  assert.equal(resolveWebProductImage("http://127.0.0.1/private.png", "A100"), "/images/a800.jpg");
  assert.equal(resolveWebProductImage("http://localhost/private.png", "B300"), "/images/h100.jpg");
  assert.equal(resolveWebProductImage("javascript:alert(1)", "RTX 5090"), "/images/rtx5090.jpg");
});

test("Web English market localizes every canonical KAI region", () => {
  assert.equal(localizeMarketRegion("华中", "en"), "Central China");
  assert.equal(localizeMarketRegion("中国大陆", "en"), "Mainland China");
  assert.equal(localizeMarketRegion("北美", "en"), "North America");
  assert.equal(localizeMarketRegion("欧洲", "en"), "Europe");
  assert.equal(localizeMarketRegion("全球 / 未披露", "en"), "Global / Undisclosed");
  assert.equal(localizeMarketRegion("global_unspecified", "en"), "Global / Undisclosed");
  assert.equal(localizeMarketRegion("北美", "zh-CN"), "北美");
});

test("hour purchases and expiry rebate estimates remain bounded by server policy", () => {
  assert.equal(clampPurchaseHours(1.9), 1);
  assert.equal(clampPurchaseHours(721), 720);
  assert.deepEqual(estimateProductExpiryRebate(100, "usage", rewardSummary), { amount: 5, ratePercent: 5 });
  assert.deepEqual(estimateProductExpiryRebate(100, "holding", rewardSummary), { amount: 0, ratePercent: 0 });
  assert.deepEqual(estimateProductExpiryRebate(100, "usage", { ...rewardSummary, minimum_order_amount: undefined }), { amount: 0, ratePercent: 0 });
  assert.deepEqual(estimateProductExpiryRebate(100, "usage", { ...rewardSummary, tiers: [] }), { amount: 0, ratePercent: 0 });
});

test("Web trend normal state auto-refreshes and renders canonical KAI regional spreads", () => {
  const panel = fs.readFileSync(new URL("../components/live-market-panel.tsx", import.meta.url), "utf8");
  const api = fs.readFileSync(new URL("../lib/mobile-market-api.ts", import.meta.url), "utf8");
  const adapter = fs.readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");

  assert.match(panel, /MARKET_AUTO_REFRESH_MS = 10_000/);
  assert.match(panel, /window\.setInterval\(\(\) => \{ void load\(true, false\); \}, MARKET_AUTO_REFRESH_MS\)/);
  assert.match(panel, /getMobileRegionalQuotes\(model\)/);
  assert.match(panel, /区域价差/);
  assert.match(panel, /card_hour_rmb_rate/);
  assert.match(api, /canonicalApiPath\(`\/products\/quote\/regional\?\$\{query\.toString\(\)\}`\)/);
  assert.match(adapter, /products\\\/quote\\\/regional/);
  assert.doesNotMatch(panel, /GetDeploying|getdeploying/i);
});

test("Web market and detail use image_url, hourly input, rebate estimate, and an order confirmation", () => {
  const market = fs.readFileSync(new URL("../components/merchant-resource-market.tsx", import.meta.url), "utf8");
  const detail = fs.readFileSync(new URL("../components/product-detail.tsx", import.meta.url), "utf8");
  const browser = fs.readFileSync(new URL("../components/market-browser.tsx", import.meta.url), "utf8");
  const serverData = fs.readFileSync(new URL("../lib/server/public-page-data.ts", import.meta.url), "utf8");

  assert.match(market, /imageUrl=\{row\.image_url\}/);
  assert.match(market, /row\.purchasable \? t\("market\.buy", "立即购买"\) : t\("market\.details", "查看详情"\)/);
  assert.doesNotMatch(market, /href: "\/(supplier|admin)\/resources"/);
  assert.match(detail, /imageUrl=\{product\.image_url\}/);
  assert.match(detail, /type="number"/);
  assert.match(detail, /DEFAULT_PURCHASE_HOURS/);
  assert.doesNotMatch(detail, /purchase_hour_options\.length > 0/);
  assert.match(detail, /到期预计返佣/);
  assert.match(detail, /role="dialog"/);
  assert.match(detail, /确认并下单/);
  assert.match(serverData, /\/api\/products\?page=1&page_size=100&market_source=kai&representative=true/);
  assert.doesNotMatch(`${market}\n${detail}\n${browser}`, /GetDeploying|getdeploying|AutoDL|算力云/i);
});
