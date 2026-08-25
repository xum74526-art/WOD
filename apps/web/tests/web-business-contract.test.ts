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

test("Web registration offers phone and Kai registration through the existing authorization route", () => {
  const panel = fs.readFileSync(new URL("../components/auth-panel.tsx", import.meta.url), "utf8");

  assert.match(panel, /role="tab"[\s\S]*?setMethod\("password"\)[\s\S]*?role="tab"[\s\S]*?setMethod\("kai"\)/);
  assert.doesNotMatch(panel, /!isRegister\s*&&\s*<button[^>]+role="tab"/);
  assert.match(panel, /kaiWebAuthorizationUrl\(mode, safeReturnPath\(\)\)/);
  assert.match(panel, /sessionStorage\.setItem\(PENDING_KAI_INTENT_KEY, mode\)/);
  assert.match(panel, /kaiError === "identity_not_bound" && pendingKaiIntent === "register"/);
  assert.match(panel, /window\.location\.replace\(`\/register\$\{suffix\}`\)/);
  assert.match(panel, /isRegister \? "Continue to Kai registration" : "Sign in with Kai"/);
});

test("released clients do not describe canonical data as coming from mobile", () => {
  const webComponents = [
    "account-dashboard.tsx",
    "auth-panel.tsx",
    "community-feed.tsx",
    "gpu-candlestick-chart.tsx",
    "merchant-resource-market.tsx",
    "mobile-account-settings.tsx",
    "mobile-assets-workspace.tsx",
    "mobile-buy-request-workspace.tsx",
    "mobile-onboarding-workspace.tsx",
    "mobile-support-workspace.tsx",
    "order-workspace.tsx",
    "payment-workspace.tsx",
    "product-shell.tsx",
    "resource-workspace.tsx",
  ].map((file) => fs.readFileSync(new URL(`../components/${file}`, import.meta.url), "utf8")).join("\n");
  const iosLocale = fs.readFileSync(new URL("../../ios/src/store/i18n.ts", import.meta.url), "utf8");

  assert.doesNotMatch(webComponents, /手机端(?:后端|数据|数据库|账户|客服)|来自手机端|与手机端|mobile (?:backend|data|account|app)/i);
  assert.doesNotMatch(iosLocale, /移动端用于查看|use the mobile app to view data/i);
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

test("Web recharge orders expose the same query, safe cancel, and restart workflow as App", () => {
  const wallet = fs.readFileSync(new URL("../components/payment-workspace.tsx", import.meta.url), "utf8");
  const api = fs.readFileSync(new URL("../lib/mobile-business-api.ts", import.meta.url), "utf8");

  assert.match(wallet, /paymentQueryNotice\(order\)/);
  assert.match(wallet, /queryRechargePayment\(row\.order_no\)/);
  assert.match(wallet, /row\.can_cancel/);
  assert.match(wallet, /cancelRechargePayment\(row\.order_no\)/);
  assert.match(wallet, /rechargeCanRestart\(row\)/);
  assert.match(wallet, /更换充值金额/);
  assert.match(wallet, /queryRechargePayment\(pendingPayment\.order_no\)/);
  assert.match(wallet, /确认充值金额/);
  assert.match(wallet, /credited_at/);
  assert.match(wallet, /rechargeStatus/);
  assert.match(wallet, /rechargeOrderNo/);
  assert.match(wallet, /withdrawalStatus/);
  assert.match(api, /page: String\(params\.page \|\| 1\)/);
  assert.match(api, /query\.set\("order_no", params\.order_no\)/);
  assert.match(api, /query\.set\("status_filter", params\.status_filter\)/);
  assert.match(wallet, /取消订单/);
  assert.match(wallet, /再来一单/);
  assert.match(wallet, /到期：/);
  assert.match(wallet, /minimumRechargeAmountCny\(paymentConfig\?\.min_amount_cny\)/);
  assert.match(wallet, /minimumWithdrawalCardHours\(withdrawalConfig\?\.min_card_hours\)/);
  assert.doesNotMatch(wallet, /min=\{paymentConfig\?\.min_amount_cny \|\| 0\.01\}/);
  assert.doesNotMatch(wallet, /min=\{withdrawalConfig\?\.min_card_hours \|\| 0\.01\}/);

  const replaceFlow = wallet.slice(wallet.indexOf("async function replaceRechargeAmount"), wallet.indexOf("function continueCheckout"));
  assert.ok(replaceFlow.indexOf("queryRechargePayment") < replaceFlow.indexOf("localStorage.removeItem"));
  const failedQueryBranch = replaceFlow.slice(replaceFlow.indexOf("catch (reason)"), replaceFlow.indexOf("finally"));
  assert.doesNotMatch(failedQueryBranch, /localStorage\.removeItem|setPendingPayment\(null\)/);
});

test("Web bank cards require identity, consent, validation, and eligible default cards", () => {
  const source = fs.readFileSync(new URL("../components/mobile-account-services.tsx", import.meta.url), "utf8");

  assert.match(source, /getVerification\(\)/);
  assert.match(source, /verification\?\.status !== "verified"/);
  assert.match(source, /readOnly placeholder="完成实名认证后自动填写"/);
  assert.match(source, /luhnCheckCardNumber\(cardNumber\)/);
  assert.match(source, /type="checkbox" checked=\{consent\}/);
  assert.match(source, /card\.reject_reason/);
  assert.match(source, /isRegisteredBankCardStatus\(card\.status\)/);
});
