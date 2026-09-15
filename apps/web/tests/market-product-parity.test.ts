import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { fallbackWebProductImage, resolveWebProductImage } from "../lib/product-image.ts";
import { clampPurchaseHours, estimateProductExpiryRebate, localizeRebateHint } from "../lib/product-purchase.ts";
import { localizeMarketRegion } from "../lib/market-localization.ts";

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
  assert.equal(localizeMarketRegion("北美", "zh-Hans"), "北美");
  assert.equal(localizeMarketRegion("华东", "zh-Hant"), "華東");
});

test("hour purchases estimate expiry rebates from the authenticated personal tier policy", () => {
  assert.equal(clampPurchaseHours(1.9), 1);
  assert.equal(clampPurchaseHours(721), 720);
  const policy = {
    month_spent: 9_900,
    current_rate: 3,
    minimum_order_amount: 10,
    cap_remaining: 100,
    rewards_enabled: true,
    tiers: [
      { max_month_spent: 10_000, rate: 3 },
      { max_month_spent: 50_000, rate: 5 },
      { max_month_spent: 100_000, rate: 7 },
      { max_month_spent: null, rate: 10 },
    ],
  };
  assert.deepEqual(estimateProductExpiryRebate(50, "usage", policy), { amount: 1.5, ratePercent: 3 });
  assert.deepEqual(estimateProductExpiryRebate(200, "usage", policy), { amount: 10, ratePercent: 5 });
  assert.deepEqual(estimateProductExpiryRebate(200, "usage", { ...policy, cap_remaining: 1.25 }), { amount: 1.25, ratePercent: 5 });
  assert.deepEqual(estimateProductExpiryRebate(100, "holding", policy), { amount: 0, ratePercent: 0 });
  assert.deepEqual(estimateProductExpiryRebate(9, "usage", policy), { amount: 0, ratePercent: 0 });
  assert.deepEqual(estimateProductExpiryRebate(100, "usage", { ...policy, rewards_enabled: false }), { amount: 0, ratePercent: 0 });
  assert.deepEqual(estimateProductExpiryRebate(100, "usage", { ...policy, cap_remaining: Number.NaN }), { amount: 0, ratePercent: 0 });
  assert.equal(localizeRebateHint("再消费 100 卡时可升至 5% 返佣", "en"), "Spend 100 more card hours to reach the 5% personal purchase rebate tier.");
  assert.equal(localizeRebateHint("再销售 200 卡时可升至 8% 返佣", "en"), "Confirm 200 more card hours in sales to reach the 8% supplier sales rebate tier.");
});

test("Web trend separates live quote polling from the heavier market catalogue", () => {
  const panel = fs.readFileSync(new URL("../components/live-market-panel.tsx", import.meta.url), "utf8");
  const chart = fs.readFileSync(new URL("../components/market-candlestick-chart.tsx", import.meta.url), "utf8");
  const api = fs.readFileSync(new URL("../lib/mobile-market-api.ts", import.meta.url), "utf8");
  const adapter = fs.readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");

  assert.match(panel, /MARKET_CATALOG_REFRESH_MS = 300_000/);
  assert.match(panel, /if \(!initialData\) void load\(false, true\)/);
  assert.match(panel, /if \(!document\.hidden\) void load\(true, false\);[\s\S]*MARKET_CATALOG_REFRESH_MS/);
  assert.match(panel, /if \(inFlight\) return/);
  assert.match(panel, /void refreshRegionalQuotes\(true\)/);
  assert.match(panel, /if \(!document\.hidden\) void refreshRegionalQuotes\(false\);[\s\S]*MARKET_CATALOG_REFRESH_MS/);
  assert.doesNotMatch(panel, /getMobileLatestMarket\(model\)/);
  assert.match(chart, /LATEST_REFRESH_MS = 300_000/);
  assert.match(chart, /if \(!document\.hidden\) void refreshLatest\(\)/);
  assert.match(chart, /onLatestRef\.current\?\.\(value\)/);
  assert.match(adapter, /PUBLIC_MARKET_LATEST_TTL_MS = 300_000/);
  assert.match(adapter, /PUBLIC_MARKET_LATEST_STALE_MS = 600_000/);
  assert.match(adapter, /createStaleTtlCache<\s*\[NextRequest, string, string, string\]/);
  assert.match(adapter, /JSON\.stringify\(\[apiOrigin, locale, queryString\]\)/);
  assert.match(adapter, /searchParams\.getAll\("model"\)/);
  assert.match(adapter, /searchParams\.getAll\("variant"\)/);
  assert.match(adapter, /searchParams\.getAll\("sources"\)/);
  assert.match(adapter, /new URLSearchParams\(\{ model, sources: "kai" \}\)/);
  assert.match(adapter, /publicMarketLatestQuery\(request\.nextUrl\.searchParams\)/);
  assert.match(adapter, /result\.body\.code !== 0/);
  assert.match(adapter, /isValidMarketLatestPayload\(result\.body\.data/);
  assert.match(adapter, /PublicMarketLatestPayloadError/);
  assert.match(adapter, /invalid_market_payload/);
  assert.match(adapter, /refreshMode: "blocking"/);
  assert.match(adapter, /canonicalPath === "market\/prices\/latest"\) return publicMarketLatest\(request\)/);
  assert.match(adapter, /publicRealtimeApiSuccess\(payload\.data, \{ source: "canonical-api" \}\)/);
  assert.match(adapter, /"Cache-Control": "private, no-store"/);
  assert.doesNotMatch(panel, /MARKET_AUTO_REFRESH_MS/);
  assert.match(panel, /getMobileRegionalQuotes\(model\)/);
  assert.match(panel, /区域价差/);
  assert.match(panel, /card_hour_rmb_rate/);
  assert.match(api, /canonicalApiPath\(`\/products\/quote\/regional\?\$\{query\.toString\(\)\}`\)/);
  assert.match(adapter, /products\\\/quote\\\/regional/);
  assert.doesNotMatch(panel, /GetDeploying|getdeploying/i);
});

test("Web market and detail keep inquiry as the safe default while preserving gated direct trade", () => {
  const market = fs.readFileSync(new URL("../components/merchant-resource-market.tsx", import.meta.url), "utf8");
  const detail = fs.readFileSync(new URL("../components/product-detail.tsx", import.meta.url), "utf8");
  const browser = fs.readFileSync(new URL("../components/market-browser.tsx", import.meta.url), "utf8");
  const locale = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");
  const serverData = fs.readFileSync(new URL("../lib/server/public-page-data.ts", import.meta.url), "utf8");

  assert.match(market, /imageUrl=\{row\.image_url\}/);
  assert.match(market, /t\("market\.inquiry", "询价"\)/);
  assert.match(market, /t\("market\.submitRequest", "提交需求"\)/);
  assert.match(market, /row\.unit_price_ch\.toLocaleString/);
  assert.match(market, /matchmakingEnabled && row\.inquiry_available !== false/);
  assert.match(market, /directTradeEnabled \? row\.purchasable \?/);
  assert.doesNotMatch(market, /href: "\/(supplier|admin)\/resources"/);
  assert.match(detail, /imageUrl=\{product\.image_url\}/);
  assert.match(detail, /type="number"/);
  assert.match(detail, /DEFAULT_PURCHASE_HOURS/);
  assert.doesNotMatch(detail, /purchase_hour_options\.length > 0/);
  assert.match(detail, /function beginInquiry\(\)/);
  assert.match(detail, /new URLSearchParams\(/);
  assert.match(detail, /\/account\/requests\?\$\{params\.toString\(\)\}/);
  assert.match(detail, /directTradeEnabled \? `\$\{product\.unit_price_ch[\s\S]*? : "询价"/);
  assert.match(detail, /提交需求/);
  assert.match(detail, /if \(!directTradeEnabled \|\| !product\?\.purchasable/);
  assert.match(detail, /matchmakingEnabled && product\.inquiry_available !== false/);
  assert.match(detail, /createDirectOrder/);
  assert.match(detail, /预计钱包扣款/);
  assert.match(detail, /确认并下单/);
  assert.match(locale, /"product\.rebate\.label": "Estimated personal purchase rebate at expiry"/);
  assert.match(locale, /"product\.rebate\.tierChange": "Your current personal tier is \{current\}%/);
  assert.doesNotMatch(`${detail}\n${locale}`, /fixed 3%|固定3%|到期返佣（3%）|Purchased card hours × 3%/i);
  assert.match(detail, /role="dialog"/);
  assert.match(serverData, /\/api\/products\?page=1&page_size=100&market_source=kai&representative=true/);
  assert.match(serverData, /\/api\/products\?page=1&page_size=100&market_source=wod/);
  assert.match(market, /market\.kai\.title/);
  assert.match(market, /market\.merchant\.title/);
  assert.match(market, /提交需求后由平台人工联系确认方案/);
  assert.match(market, /提交需求后由对应商家人工联系确认方案/);
  assert.doesNotMatch(detail, /product\.market_source !== "kai"/);
  assert.doesNotMatch(`${market}\n${detail}\n${browser}`, /GetDeploying|getdeploying|AutoDL|算力云/i);
});

test("Web rebate center separates personal purchases from supplier confirmed sales", () => {
  const supplier = fs.readFileSync(new URL("../components/mobile-supplier-operations.tsx", import.meta.url), "utf8");
  const account = fs.readFileSync(new URL("../components/mobile-account-services.tsx", import.meta.url), "utf8");
  const api = fs.readFileSync(new URL("../lib/mobile-business-api.ts", import.meta.url), "utf8");
  const locale = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

  assert.match(api, /getUserRebate\(\)/);
  assert.match(api, /canonicalApiPath\("\/user\/rebate"\)/);
  assert.match(api, /month_entitled: number/);
  assert.match(api, /cap_used: number/);
  assert.match(api, /cap_remaining: number/);
  assert.match(supplier, /Promise\.all\(\[getUserRebate\(\), getSupplierRebate\(\)\]\)/);
  assert.match(supplier, /personal\?\.tiers \?\? \[\]/);
  assert.match(supplier, /supplier\?\.tiers \?\? \[\]/);
  assert.match(supplier, /personal\?\.monthly_cap \?\? 0/);
  assert.match(supplier, /supplier\?\.monthly_cap \?\? 0/);
  assert.doesNotMatch(supplier, /PERSONAL_REBATE_TIERS|SUPPLIER_REBATE_TIERS|20_000|50_000/);
  assert.match(supplier, /返佣基数为本月已确认销售卡时总额，不是平台服务费/);
  assert.doesNotMatch(supplier, /data\?\.service_fee_rate/);
  assert.match(account, /个人购买返佣/);
  assert.match(account, /本月应计 \{entitled\} · 已用额度 \{used\} · 剩余额度 \{remaining\} · 月度上限 \{cap\} 卡时/);
  assert.match(locale, /"rebate\.personal\.title": "Personal Purchase Rebate"/);
  assert.match(locale, /"rebate\.supplier\.title": "Supplier Sales Rebate"/);
  assert.match(locale, /not the platform service fee/);
});
