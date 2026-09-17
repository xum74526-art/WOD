import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  buyRequestAdditionalRequirements,
  buyRequestIntentSignature,
  directOrderIntentSignature,
  ensureBuyRequestIntent,
  ensureDirectOrderIntent,
  ensureRenewalIntent,
  ensureSupplierDeviceIntent,
  hourlyOrderBody,
  kaiPricingQuery,
  normalizeBuyRequestContactPhone,
  renewalIntentSignature,
  supplierDeviceIntentSignature,
  webRequestId,
} from "../lib/web-business-contract.ts";
import { communityDisplayText } from "../lib/community-ui.ts";

test("legacy community brand values are renamed for display without changing backend identifiers", () => {
  assert.equal(communityDisplayText("WOD资讯", "wod-market"), "算力星图资讯");
  assert.equal(communityDisplayText("WOD 算力行情", "wod-market"), "算力星图 算力行情");
  assert.equal(communityDisplayText("ZTW 算力行情", "wod-market"), "算力星图 算力行情");
  assert.equal(communityDisplayText("WOD 行情更新", "user-post"), "WOD 行情更新");
  assert.equal(communityDisplayText("资源编号 WOD-P-12", "wod-market"), "资源编号 WOD-P-12");

  const feed = fs.readFileSync(new URL("../components/community-feed.tsx", import.meta.url), "utf8");
  assert.match(feed, /communityDisplayText\(row\.source_name \|\| row\.source_author, row\.source_key\)/);
  assert.match(feed, /communityDisplayText\(row\.author_name \|\| row\.source_author \|\| row\.source_name, row\.source_key\)/);
  assert.match(feed, /communityDisplayText\(row\.content, row\.source_key\)/);
});

test("all live market requests force KAI Pricing as the only source", () => {
  const query = new URLSearchParams(kaiPricingQuery({ model: "H100", variant: "80GB", sources: "vast,autodl" }));
  assert.equal(query.get("sources"), "kai");
  assert.equal(query.get("model"), "H100");
});

test("buy-request contact phone matches the API storage contract", () => {
  assert.equal(normalizeBuyRequestContactPhone(" +86 (139) 1000-0001 "), "+8613910000001");
  assert.equal(normalizeBuyRequestContactPhone("1".repeat(20)), "1".repeat(20));
  assert.equal(normalizeBuyRequestContactPhone(`+${"1".repeat(15)}`), `+${"1".repeat(15)}`);
  assert.equal(normalizeBuyRequestContactPhone("12345"), null);
  assert.equal(normalizeBuyRequestContactPhone("86+13910000001"), null);
  assert.equal(normalizeBuyRequestContactPhone("+0123456789"), null);
  assert.equal(normalizeBuyRequestContactPhone("139.1000.0001"), null);
  assert.equal(normalizeBuyRequestContactPhone(`+${"1".repeat(20)}`), null);
  assert.equal(normalizeBuyRequestContactPhone(`+${"1".repeat(16)}`), null);
  assert.equal(normalizeBuyRequestContactPhone("1".repeat(21)), null);

  const workspace = fs.readFileSync(new URL("../components/mobile-buy-request-workspace.tsx", import.meta.url), "utf8");
  assert.match(workspace, /normalizeBuyRequestContactPhone\(form\.phone\)/);
  assert.match(workspace, /type="tel" inputMode="tel" maxLength=\{32\}/);
  assert.match(workspace, /phone: event\.target\.value\.slice\(0, 32\)/);
});

test("buy-request notes and GPU variants remain compatible across Web and App", () => {
  assert.equal(buyRequestAdditionalRequirements({ note: "Web 补充需求" }), "Web 补充需求");
  assert.equal(buyRequestAdditionalRequirements({ note: "新补充需求", remark: "旧补充需求" }), "新补充需求");
  assert.equal(buyRequestAdditionalRequirements({ remark: "旧 App 补充需求" }), "旧 App 补充需求");
  assert.equal(buyRequestAdditionalRequirements({ note: "  ", remark: "旧值" }), "旧值");
  assert.equal(buyRequestAdditionalRequirements({}), "");

  const workspace = fs.readFileSync(new URL("../components/mobile-buy-request-workspace.tsx", import.meta.url), "utf8");
  const admin = fs.readFileSync(new URL("../components/admin-buy-request-workspace.tsx", import.meta.url), "utf8");
  assert.match(workspace, /gpu_variant: initialPrefill\?\.gpu_variant \|\| undefined/);
  assert.doesNotMatch(workspace, /\n\s+gpu_variant: initialPrefill\?\.gpu_variant,\n/);
  assert.match(workspace, /note: additionalRequirements,[\s\S]*remark: additionalRequirements/);
  assert.match(workspace, /row\.gpu_variant \? ` \$\{row\.gpu_variant\}` : ""/);
  assert.match(workspace, /detail\.request\.gpu_variant \? ` \$\{detail\.request\.gpu_variant\}` : ""/);
  assert.match(workspace, /detailRequirementNote && <div className="workspace-service-note">/);
  assert.match(admin, /detailRequirementNote && <div className="workspace-service-note">/);
});

test("new and renewal orders use integer hours plus a Web request id", () => {
  const requestId = webRequestId("order", "12345678-1234-1234-1234-123456789abc");
  assert.deepEqual(hourlyOrderBody(24, requestId), { hours: 24, client_request_id: requestId });
  assert.equal("cycle_days" in hourlyOrderBody(24, requestId), false);
  assert.throws(() => hourlyOrderBody(1.5, requestId), /整数小时/);
  assert.throws(() => hourlyOrderBody(721, requestId), /1 至 720/);
});

test("renewal retries reuse one request id until the order or hours change or confirmation is cancelled", () => {
  let sequence = 0;
  const createUuid = () => `12345678-1234-1234-1234-${String(++sequence).padStart(12, "0")}`;
  const signature = renewalIntentSignature(17, 24);
  const first = ensureRenewalIntent(null, signature, createUuid);
  const retry = ensureRenewalIntent(first, signature, createUuid);

  assert.equal(signature, JSON.stringify([17, 24]));
  assert.equal(retry.requestId, first.requestId);
  assert.equal(sequence, 1);

  const changedHours = ensureRenewalIntent(retry, renewalIntentSignature(17, 48), createUuid);
  assert.notEqual(changedHours.requestId, first.requestId);

  const changedOrder = ensureRenewalIntent(changedHours, renewalIntentSignature(18, 48), createUuid);
  assert.notEqual(changedOrder.requestId, changedHours.requestId);

  const afterCancel = ensureRenewalIntent(null, signature, createUuid);
  assert.notEqual(afterCancel.requestId, first.requestId);
  assert.equal(sequence, 4);
});

test("Web renewal submission keeps the same explicit id through retries", () => {
  const api = fs.readFileSync(new URL("../lib/commerce-api.ts", import.meta.url), "utf8");
  const workspace = fs.readFileSync(new URL("../components/order-workspace.tsx", import.meta.url), "utf8");
  const renewal = api.slice(api.indexOf("export function renewOrder"), api.indexOf("export function createDirectOrder"));
  const renewalAction = workspace.slice(workspace.indexOf("function submitRenewal"), workspace.indexOf("function deliveryNote"));

  assert.match(renewal, /renewOrder\(id: number, hours: number, clientRequestId: string\)/);
  assert.match(renewal, /"Idempotency-Key": clientRequestId/);
  assert.match(renewal, /hourlyOrderBody\(hours, clientRequestId\)/);
  assert.doesNotMatch(renewal, /randomUUID/);
  assert.match(renewalAction, /const orderId = detail\.id;\s+const hours = renewalHour;/);
  assert.match(renewalAction, /if \(!detail \|\| busy \|\| renewalSubmissionInFlight\.current\) return;/);
  assert.match(renewalAction, /ensureRenewalIntent\(\s+pendingRenewalIntent\.current,\s+renewalIntentSignature\(orderId, hours\)/);
  assert.match(renewalAction, /pendingRenewalIntent\.current = intent;/);
  assert.match(renewalAction, /if \(!window\.confirm[\s\S]*?pendingRenewalIntent\.current = null;\s+return;/);
  assert.match(renewalAction, /renewalSubmissionInFlight\.current = true;/);
  assert.match(renewalAction, /await renewOrder\(orderId, hours, intent\.requestId\);\s+pendingRenewalIntent\.current = null;[\s\S]*?renewalSubmissionInFlight\.current = false;/);
  assert.equal(renewalAction.match(/pendingRenewalIntent\.current = null/g)?.length, 2);
});

test("Web asset and order follow-up links preserve shared request context", () => {
  const assets = fs.readFileSync(new URL("../components/mobile-assets-workspace.tsx", import.meta.url), "utf8");
  const orders = fs.readFileSync(new URL("../components/order-workspace.tsx", import.meta.url), "utf8");
  const adapter = fs.readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");

  assert.match(assets, /requestCreateHref\(\{ product_id: item\.product_id, source: "existing_asset"[\s\S]*?gpu_hours: 24 \}\)/);
  assert.match(orders, /supplier_id: order\.supplier_id/);
  assert.match(orders, /source: order\.market_source \|\| order\.seller_type \|\| "existing_order"/);
  assert.match(orders, /seller_name: sellerCopy\(order\)/);
  assert.match(orders, /const originalHours = Number\(order\.duration_hours \?\? order\.purchase_hours\)/);
  assert.match(orders, /gpu_hours: Number\.isFinite\(originalHours\) && originalHours >= 1 \? originalHours : 24/);
  assert.match(orders, /href=\{renewalRequestHref\(detail\)\}/);
  assert.match(adapter, /market_source: text\(item\.market_source\) === "kai"/);
  assert.doesNotMatch(orders, /gpu_hours=24`/);
});

test("direct-order retries reuse one request id until the intent changes or is cancelled", () => {
  let sequence = 0;
  const createUuid = () => `12345678-1234-1234-1234-${String(++sequence).padStart(12, "0")}`;
  const input = {
    product_id: 17,
    quantity: 2,
    hours: 24,
    purchase_type: "usage" as const,
    expected_unit_price_card_hours: 3.25,
  };
  const signature = directOrderIntentSignature(input);
  const first = ensureDirectOrderIntent(null, signature, createUuid);
  const retry = ensureDirectOrderIntent(first, signature, createUuid);

  assert.equal(retry.requestId, first.requestId);
  assert.equal(sequence, 1);

  const changed = ensureDirectOrderIntent(
    retry,
    directOrderIntentSignature({ ...input, hours: 48 }),
    createUuid,
  );
  assert.notEqual(changed.requestId, first.requestId);

  const afterCancel = ensureDirectOrderIntent(null, signature, createUuid);
  assert.notEqual(afterCancel.requestId, first.requestId);
  assert.equal(sequence, 3);
});

test("Web direct-order submission keeps the same explicit id in its body and header", () => {
  const api = fs.readFileSync(new URL("../lib/commerce-api.ts", import.meta.url), "utf8");
  const detail = fs.readFileSync(new URL("../components/product-detail.tsx", import.meta.url), "utf8");
  const directOrder = api.slice(api.indexOf("export function createDirectOrder"), api.indexOf("export function listSshKeys"));

  assert.match(directOrder, /createDirectOrder\([^)]*clientRequestId: string\)/);
  assert.match(directOrder, /"Idempotency-Key": clientRequestId/);
  assert.match(directOrder, /hourlyOrderBody\(input\.hours, clientRequestId\)/);
  assert.doesNotMatch(directOrder, /randomUUID/);
  assert.match(detail, /if \(orderSubmissionInFlight\.current\) return;/);
  assert.match(detail, /createDirectOrder\(pending\.input, pending\.requestId\)/);
  assert.match(detail, /pendingOrderIntent\.current = null;/);
});

test("buy-request retries reuse one request id until the payload changes or the form closes", () => {
  let sequence = 0;
  const createUuid = () => `12345678-1234-1234-1234-${String(++sequence).padStart(12, "0")}`;
  const input = {
    request_type: "online",
    gpu_model: "H100",
    quantity: 2,
    gpu_hours: 24,
    currency: "CNY",
    requirements: { source: "kai", note: "CUDA 12" },
    contact: "采购人",
    phone: "13800138000",
    expires_in_hours: 72,
  };
  const signature = buyRequestIntentSignature(input);
  const first = ensureBuyRequestIntent(null, signature, createUuid);
  const retry = ensureBuyRequestIntent(first, signature, createUuid);

  assert.equal(signature, JSON.stringify(input));
  assert.equal(retry.requestId, first.requestId);
  assert.equal(sequence, 1);

  const changed = ensureBuyRequestIntent(
    retry,
    buyRequestIntentSignature({ ...input, gpu_hours: 48 }),
    createUuid,
  );
  assert.notEqual(changed.requestId, first.requestId);

  const afterClose = ensureBuyRequestIntent(null, signature, createUuid);
  assert.notEqual(afterClose.requestId, first.requestId);
  assert.match(first.requestId, /^web-buy-request-/);
  assert.equal(sequence, 3);
});

test("Web buy-request submission has a synchronous lock and sends the stable id in JSON", () => {
  const api = fs.readFileSync(new URL("../lib/mobile-buy-request-api.ts", import.meta.url), "utf8");
  const workspace = fs.readFileSync(new URL("../components/mobile-buy-request-workspace.tsx", import.meta.url), "utf8");
  const createRequest = workspace.slice(workspace.indexOf("async function create("), workspace.indexOf("async function submitQuote"));
  const toggleForm = workspace.slice(workspace.indexOf("function toggleCreateForm"), workspace.indexOf("async function create("));

  assert.match(createRequest, /if \(requestSubmissionInFlight\.current\) return;/);
  assert.ok(createRequest.indexOf("requestSubmissionInFlight.current = true") < createRequest.indexOf("await createMobileBuyRequest"));
  assert.match(createRequest, /buyRequestIntentSignature\(input\)/);
  assert.match(createRequest, /client_request_id: intent\.requestId/);
  assert.match(createRequest, /pendingBuyRequestIntent\.current = null;[\s\S]*?setCreating\(false\)/);
  assert.match(createRequest, /finally \{[\s\S]*?requestSubmissionInFlight\.current = false;/);
  const failedRequest = createRequest.slice(createRequest.indexOf("catch (reason)"), createRequest.indexOf("finally"));
  assert.doesNotMatch(failedRequest, /pendingBuyRequestIntent\.current = null/);
  assert.match(toggleForm, /if \(creating\) pendingBuyRequestIntent\.current = null;/);
  assert.match(api, /MobileBuyRequestInput[\s\S]*?client_request_id: string/);
  assert.match(api, /createMobileBuyRequest\(input: MobileBuyRequestInput\)/);
  assert.match(api, /body: JSON\.stringify\(input\)/);
  assert.doesNotMatch(api, /randomUUID/);
});

test("supplier resource retries reuse one request id until the create payload changes", () => {
  let sequence = 0;
  const createUuid = () => `12345678-1234-1234-1234-${String(++sequence).padStart(12, "0")}`;
  const input = {
    name: "H100 80GB",
    gpu_model: "H100",
    memory: "80GB",
    price: 24.8,
    stock: 4,
    region_code: "east_china",
    region_name: "华东",
    city: "上海",
  };
  const signature = supplierDeviceIntentSignature(input);
  const first = ensureSupplierDeviceIntent(null, signature, createUuid);
  const retry = ensureSupplierDeviceIntent(first, signature, createUuid);
  const changed = ensureSupplierDeviceIntent(
    retry,
    supplierDeviceIntentSignature({ ...input, stock: 5 }),
    createUuid,
  );

  assert.equal(retry.requestId, first.requestId);
  assert.notEqual(changed.requestId, first.requestId);
  assert.match(first.requestId, /^web-supplier-device-/);
  assert.equal(sequence, 2);
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

  assert.match(panel, /value=\{name\}[^\r\n]*minLength=\{2\} maxLength=\{64\}/);
  assert.match(panel, /value=\{password\}[^\r\n]*minLength=\{isRegister \? 6 : 1\} maxLength=\{64\}/);
  assert.match(panel, /value=\{inviteCode\}[^\r\n]*maxLength=\{16\}/);
  assert.match(panel, /role="tab"[\s\S]*?setMethod\("password"\)[\s\S]*?role="tab"[\s\S]*?setMethod\("kai"\)/);
  assert.doesNotMatch(panel, /!isRegister\s*&&\s*<button[^>]+role="tab"/);
  assert.match(panel, /kaiWebAuthorizationUrl\(mode, safeReturnPath\(\)\)/);
  assert.match(panel, /sessionStorage\.setItem\(PENDING_KAI_INTENT_KEY, mode\)/);
  assert.match(panel, /kaiError === "identity_not_bound" && pendingKaiIntent === "register"/);
  assert.match(panel, /window\.location\.replace\(`\/register\$\{suffix\}`\)/);
  assert.match(panel, /isRegister \? t\("auth\.kai\.continueRegistration"/);
  assert.match(panel, /t\("auth\.kai\.signIn"/);
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
  const chart = fs.readFileSync(new URL("../components/market-candlestick-chart.tsx", import.meta.url), "utf8");
  const chartMath = fs.readFileSync(new URL("../lib/market-candlestick-chart.ts", import.meta.url), "utf8");
  const summary = adapter.slice(
    adapter.indexOf("async function buildMarketSummary"),
    adapter.indexOf("async function accountSummary"),
  );

  assert.match(summary, /\/api\/market\/prices\/candles/);
  assert.match(summary, /sources:\s*"kai"/);
  assert.match(summary, /close_price_card_hours/);
  assert.match(summary, /median_price_card_hours/);
  assert.doesNotMatch(summary, /\/api\/market\/prices\/history/);
  assert.match(panel, /`\$\{item\.gpu_model\} \$\{item\.gpu_variant\}`/);
  assert.match(panel, /MarketCandlestickChart/);
  assert.match(chart, /getMobileMarketCandles/);
  assert.match(chart, /median_price_card_hours/);
  assert.match(chartMath, /open_price_card_hours/);
  assert.match(chartMath, /close_price_card_hours/);
});

test("Web compute catalogue separates representative KAI offers from individual merchant listings", () => {
  const adapter = fs.readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");
  const market = fs.readFileSync(new URL("../components/merchant-resource-market.tsx", import.meta.url), "utf8");
  const detail = fs.readFileSync(new URL("../components/product-detail.tsx", import.meta.url), "utf8");
  const home = fs.readFileSync(new URL("../components/home-page-content.tsx", import.meta.url), "utf8");
  const api = fs.readFileSync(new URL("../lib/commerce-api.ts", import.meta.url), "utf8");

  assert.match(adapter, /requestedPage = Math\.max\(1,[\s\S]*?query\.set\("page", String\(requestedPage\)\)/);
  assert.match(adapter, /requestedPageSize[\s\S]*?query\.set\("page_size", String\(requestedPageSize\)\)/);
  assert.doesNotMatch(adapter, /query\.set\("page", "1"\)/);
  assert.doesNotMatch(adapter, /total: products\.length, total_pages: 1/);
  assert.match(adapter, /marketSource === "kai"[\s\S]*?query\.set\("representative", "true"\)/);
  assert.match(adapter, /else query\.delete\("representative"\)/);
  assert.match(api, /listPublicProducts\(marketSource\?: "kai" \| "wod", page = 1, pageSize = 24\)/);
  assert.match(market, /listPublicProducts\(source, page, MARKET_PAGE_SIZE\)/);
  assert.match(market, /new Map\(current\.map\(\(row\) => \[row\.id, row\]\)\)/);
  assert.match(market, /key=\{row\.id\}/);
  assert.match(market, /append \? mergeProducts\(current\[source\]\.rows, result\.data\)/);
  assert.match(market, /loadSourcePage\(activeSource, catalog\.page \+ 1, true\)/);
  assert.match(market, /market\.kai\.title/);
  assert.match(market, /market\.merchant\.title/);
  assert.match(market, /row\.seller_name/);
  assert.match(market, /row\.supplier_rating/);
  assert.match(market, /row\.supplier_order_count/);
  assert.match(market, /row\.resource_claim_source/);
  assert.match(market, /提交需求后由平台人工联系确认方案/);
  assert.match(market, /提交需求后由对应商家人工联系确认方案/);
  assert.match(market, /market\.inquiry/);
  assert.match(market, /market\.submitRequest/);
  assert.match(market, /row\.unit_price_ch\.toLocaleString/);
  assert.match(market, /matchmakingEnabled && row\.inquiry_available !== false/);
  assert.match(detail, /beginInquiry/);
  assert.match(detail, /\/account\/requests/);
  assert.match(detail, /createDirectOrder/);
  assert.match(detail, /if \(!directTradeEnabled \|\| !product\?\.purchasable/);
  assert.match(detail, /matchmakingEnabled && product\.inquiry_available !== false/);
  assert.match(detail, /product\.seller_name/);
  assert.match(detail, /product\.fulfillment_mode/);
  assert.match(detail, /product\.resource_claim_source/);
  assert.doesNotMatch(detail, /product\.market_source !== "kai"/);
  assert.match(detail, /服务价格/);
  assert.match(detail, /询价/);
  assert.match(detail, /预计钱包扣款/);
  assert.match(adapter, /expected_unit_price_card_hours: number\(body\.expected_unit_price_card_hours\)/);
  assert.match(adapter, /const purchaseUnit = text\(item\.purchase_unit, "hour"\)/);
  assert.match(adapter, /resource_claim_source: resourceClaimSource/);
  assert.doesNotMatch(adapter, /server_online: Boolean\(item\.purchasable\)/);
  assert.doesNotMatch(adapter, /marketSource === "kai" \? "hour" : "day"/);
  assert.match(adapter, /Boolean\(item\.can_renew\)/);
  assert.doesNotMatch(adapter, /\["completed", "running"\][\s\S]*?available\.push\("renew"\)/);
  const serverData = fs.readFileSync(new URL("../lib/server/public-page-data.ts", import.meta.url), "utf8");
  assert.match(serverData, /\/api\/products\?page=1&page_size=100&market_source=kai&representative=true/);
  assert.match(serverData, /\/api\/products\?page=1&page_size=100&market_source=wod/);
  assert.match(serverData, /const purchaseUnit = text\(item\.purchase_unit, "hour"\)/);
  assert.match(serverData, /resource_claim_source: resourceClaimSource/);
  assert.doesNotMatch(`${home}\n${market}\n${detail}`, /Agent (?:在线|自动授权|状态)|已核验的服务器|审核服务器与 Agent/);
});

test("Web supplier order workspace exposes the canonical SSH delivery action and seller state", () => {
  const adapter = fs.readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");
  const orders = fs.readFileSync(new URL("../components/order-workspace.tsx", import.meta.url), "utf8");

  assert.match(adapter, /\/api\/orders\/\$\{id\}\/deliver/);
  assert.match(adapter, /seller_type: sellerType/);
  assert.match(adapter, /fulfillment_mode: fulfillmentMode/);
  assert.match(adapter, /status: canonicalStatus/);
  assert.doesNotMatch(adapter, /function mapOrderStatus/);
  assert.match(adapter, /delivered_at: text\(item\.delivered_at\) \|\| null/);
  assert.match(adapter, /buyer_confirmed_at: text\(item\.confirmed_at\) \|\| null/);
  assert.doesNotMatch(adapter, /item\.status === "delivering" \? item\.created_at/);
  assert.match(orders, /markOrderDelivered/);
  assert.match(orders, /提交 SSH 交付/);
  assert.match(orders, /当前履约状态/);
  assert.match(orders, /卖方提交交付/);
  assert.match(orders, /买家验收/);
  assert.doesNotMatch(orders, /Agent 已下发买家 SSH 公钥/);
});

test("Web exposes real merchant operations and keeps admission separate from identity review", () => {
  const header = fs.readFileSync(new URL("../components/site-header.tsx", import.meta.url), "utf8");
  const shell = fs.readFileSync(new URL("../components/product-shell.tsx", import.meta.url), "utf8");
  const apply = fs.readFileSync(new URL("../app/supplier/apply/page.tsx", import.meta.url), "utf8");
  const review = fs.readFileSync(new URL("../components/supplier-review.tsx", import.meta.url), "utf8");
  const resources = fs.readFileSync(new URL("../components/resource-workspace.tsx", import.meta.url), "utf8");
  const oldSupplierServers = fs.readFileSync(new URL("../app/supplier/servers/page.tsx", import.meta.url), "utf8");
  const oldAdminResources = fs.readFileSync(new URL("../app/admin/resources/page.tsx", import.meta.url), "utf8");
  const adminDashboard = fs.readFileSync(new URL("../components/admin-dashboard.tsx", import.meta.url), "utf8");

  assert.match(header, /href="\/supplier\/resources"/);
  assert.match(shell, /href: "\/supplier\/resources"/);
  assert.match(shell, /href: "\/admin\/suppliers"/);
  assert.match(shell, /href: "\/admin\/disputes"/);
  assert.match(shell, /href: "\/admin\/kyc"/);
  assert.match(shell, /href: "\/admin\/bank-cards"/);
  assert.match(shell, /href: "\/admin\/withdrawals"/);
  assert.match(apply, /入驻资料和主体实名认证分别提交、分别审核/);
  assert.match(apply, /可以先提交入驻资料/);
  assert.doesNotMatch(apply, /先完成主体实名认证，再提交商家入驻申请/);
  assert.match(review, /identity_verified/);
  assert.match(review, /page_size: PAGE_SIZE/);
  assert.match(review, /load\(status, search, page \+ 1, true\)/);
  assert.match(resources, /资源参数与可售库存由商家自行申报/);
  assert.match(oldSupplierServers, /redirect\("\/supplier\/resources"\)/);
  assert.match(oldAdminResources, /redirect\("\/admin\/suppliers"\)/);
  assert.doesNotMatch(adminDashboard, /SERVER VERIFIED/);
  assert.match(adminDashboard, /管理员统一处理需求、用户、订单、充值、实名、银行卡和提现/);
  assert.doesNotMatch(`${shell}\n${adminDashboard}`, /FINANCE ADMIN|独立财务管理员|财务管理员白名单/);
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

test("seller resource workspace uses the backend card-hour price contract", () => {
  const resource = fs.readFileSync(new URL("../components/resource-workspace.tsx", import.meta.url), "utf8");
  const supplierApi = fs.readFileSync(new URL("../lib/supplier-api.ts", import.meta.url), "utf8");

  assert.match(resource, /每 GPU 小时价格（卡时）/);
  assert.match(resource, /selected\.price\.toFixed\(4\).*卡时 \/ GPU·小时/);
  assert.doesNotMatch(resource, /每 GPU 小时价格（CNY）|selected\.price\.toFixed\(4\).*CNY/);
  assert.match(supplierApi, /MobileSupplierDevice[\s\S]*version: number/);
  assert.match(supplierApi, /expected_version: expectedVersion/);
  assert.match(resource, /updateMobileSupplierDevice\(selected\.id, selected\.version, changes\)/);
  assert.match(resource, /updateMobileSupplierDevice\(item\.id, item\.version/);
  assert.match(resource, /deleteMobileSupplierDevice\(item\.id, item\.version\)/);
  assert.match(resource, /reason instanceof ApiError/);
  assert.match(resource, /reason\.status !== 409/);
  assert.match(resource, /商品信息已发生变化，请确认最新库存后重新编辑/);
  assert.match(resource, /if \(stock !== selected\.stock\) changes\.stock = stock/);
  assert.match(resource, /if \(submissionInFlight\.current\) return/);
  assert.match(resource, /type="button" disabled=\{busy\} onClick=\{\(\) => \{/);
  assert.match(resource, /supplierDeviceIntentSignature\(input\)/);
  assert.match(resource, /client_request_id: intent\.requestId/);
  assert.match(resource, /pendingCreateIntent\.current = null/);
  assert.match(supplierApi, /MobileSupplierDeviceCreate[\s\S]*client_request_id: string/);
  assert.match(supplierApi, /createMobileSupplierDevice\(input: MobileSupplierDeviceCreate\)/);
});

test("Web wallet keeps safe history actions and capability-gates future money movement", () => {
  const wallet = fs.readFileSync(new URL("../components/payment-workspace.tsx", import.meta.url), "utf8");
  const api = fs.readFileSync(new URL("../lib/mobile-business-api.ts", import.meta.url), "utf8");

  assert.match(wallet, /paymentQueryNotice\(order\)/);
  assert.match(wallet, /queryRechargePayment\(row\.order_no\)/);
  assert.match(wallet, /row\.can_cancel/);
  assert.match(wallet, /cancelRechargePayment\(row\.order_no\)/);
  assert.match(wallet, /queryRechargePayment\(pendingPayment\.order_no\)/);
  assert.match(wallet, /credited_at/);
  assert.match(wallet, /rechargeStatus/);
  assert.match(wallet, /rechargeOrderNo/);
  assert.match(wallet, /withdrawalStatus/);
  assert.match(api, /page: String\(params\.page \|\| 1\)/);
  assert.match(api, /query\.set\("order_no", params\.order_no\)/);
  assert.match(api, /query\.set\("status_filter", params\.status_filter\)/);
  assert.match(wallet, /取消订单/);
  assert.match(wallet, /到期：/);
  assert.match(wallet, /minimumRechargeAmountCny\(paymentConfig\?\.min_amount_cny\)/);
  assert.match(wallet, /minimumWithdrawalCardHours\(withdrawalConfig\?\.min_card_hours\)/);
  assert.doesNotMatch(wallet, /min=\{paymentConfig\?\.min_amount_cny \|\| 0\.01\}/);
  assert.doesNotMatch(wallet, /min=\{withdrawalConfig\?\.min_card_hours \|\| 0\.01\}/);

  const rendered = wallet.slice(wallet.indexOf("return <section"));
  assert.match(rendered, /在线充值与提现暂未开放/);
  assert.match(wallet, /const rechargeEntryEnabled = directTradeEnabled && capabilities\.recharge_enabled === true/);
  assert.match(wallet, /const withdrawalEntryEnabled = directTradeEnabled && capabilities\.withdraw_enabled === true/);
  assert.match(rendered, /rechargeEntryEnabled && pendingState === "pending"/);
  assert.match(rendered, /继续支付/);
  assert.match(rendered, /更换充值金额/);
  assert.match(rendered, /再来一单/);
  assert.match(rendered, /账户充值/);
  assert.match(rendered, /申请提现/);

  const replaceFlow = wallet.slice(wallet.indexOf("async function replaceRechargeAmount"), wallet.indexOf("function continueCheckout"));
  assert.ok(replaceFlow.indexOf("queryRechargePayment") < replaceFlow.indexOf("localStorage.removeItem"));
  const failedQueryBranch = replaceFlow.slice(replaceFlow.indexOf("catch (reason)"), replaceFlow.indexOf("finally"));
  assert.doesNotMatch(failedQueryBranch, /localStorage\.removeItem|setPendingPayment\(null\)/);
});

test("Web matchmaking selection requests platform coordination without creating a financial order", () => {
  const workspace = fs.readFileSync(new URL("../components/mobile-buy-request-workspace.tsx", import.meta.url), "utf8");
  const buyRequestApi = fs.readFileSync(new URL("../lib/mobile-buy-request-api.ts", import.meta.url), "utf8");
  const requestPage = fs.readFileSync(new URL("../app/account/requests/page.tsx", import.meta.url), "utf8");
  const paymentPage = fs.readFileSync(new URL("../app/payment/[paymentNo]/page.tsx", import.meta.url), "utf8");
  const paymentGate = fs.readFileSync(new URL("../components/capability-payment-checkout.tsx", import.meta.url), "utf8");

  assert.match(workspace, /contact: form\.contact\.trim\(\)/);
  assert.match(workspace, /normalizeBuyRequestContactPhone\(form\.phone\)/);
  assert.match(workspace, /region: normalizeInquiryRegionRequirement\(initialPrefill\?\.region\)/);
  assert.match(workspace, /product_id: initialPrefill\?\.product_id/);
  assert.match(workspace, /supplier_id: initialPrefill\?\.supplier_id/);
  assert.match(workspace, /提交不会扣除卡时，也不会自动生成订单/);
  assert.match(workspace, /请等待工作人员联系确认/);
  assert.match(workspace, /selectMobileBuyQuote/);
  assert.match(workspace, /const snapshot = quoteSelectionSnapshot\(item\)/);
  assert.match(workspace, /selectMobileBuyQuote\(requestId, item\.id, snapshot\.revisionId\)/);
  assert.doesNotMatch(workspace, /latestQuote\(item\)\.id/);
  assert.match(buyRequestApi, /expected_revision_id: expectedRevisionId/);
  assert.match(buyRequestApi, /body: JSON\.stringify/);
  assert.match(workspace, /result\.commerce_mode === "matchmaking"/);
  assert.match(workspace, /当前未创建资金订单/);
  assert.match(requestPage, /positiveNumber\(query\.product_id\)/);
  assert.match(requestPage, /gpu_model: first\(query\.gpu_model\)/);
  assert.match(paymentPage, /CapabilityPaymentCheckout/);
  assert.match(paymentGate, /capabilities\.direct_trade_enabled === true && capabilities\.payment_enabled === true/);
  assert.match(paymentGate, /<PingxxCheckout/);
  assert.match(paymentGate, /在线支付暂未开放/);
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
