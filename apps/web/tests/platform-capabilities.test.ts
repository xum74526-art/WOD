import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("Web capabilities use the canonical same-origin adapter and fail closed", () => {
  const adapter = fs.readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");
  const model = fs.readFileSync(new URL("../lib/platform-capabilities.ts", import.meta.url), "utf8");
  const hook = fs.readFileSync(new URL("../lib/use-platform-capabilities.ts", import.meta.url), "utf8");

  const routeStart = adapter.indexOf('path === "canonical/platform/capabilities"');
  const routeEnd = adapter.indexOf('path === "public/products"', routeStart);
  assert.ok(routeStart >= 0 && routeEnd > routeStart);
  const capabilityRoute = adapter.slice(routeStart, routeEnd);
  assert.match(capabilityRoute, /upstream\(request, "\/api\/platform\/capabilities", \{ auth: false \}\)/);
  assert.doesNotMatch(capabilityRoute, /revalidate/);

  assert.match(model, /commerce_mode: "matchmaking"/);
  assert.match(model, /direct_trade_enabled: false/);
  assert.match(model, /holding_trade_enabled: false/);
  assert.match(model, /payment_enabled: false/);
  assert.match(model, /const directTradeEnabled = source\.direct_trade_enabled === true/);
  assert.match(model, /holding_trade_enabled: directTradeEnabled && source\.holding_trade_enabled === true/);
  assert.match(model, /payment_enabled: directTradeEnabled && source\.payment_enabled === true/);
  assert.match(model, /canonicalApiPath\("\/platform\/capabilities"\)/);
  assert.match(hook, /useState<PlatformCapabilities>\(FAIL_CLOSED_PLATFORM_CAPABILITIES\)/);
  assert.match(hook, /catch \{\s*setCapabilities\(FAIL_CLOSED_PLATFORM_CAPABILITIES\)/);
});

test("matchmaking availability is independent from direct purchasability", () => {
  const adapter = fs.readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");
  const market = fs.readFileSync(new URL("../components/merchant-resource-market.tsx", import.meta.url), "utf8");
  const detail = fs.readFileSync(new URL("../components/product-detail.tsx", import.meta.url), "utf8");

  assert.match(adapter, /inquiry_available: item\.inquiry_available !== false/);
  assert.match(adapter, /interaction_mode:/);
  assert.match(market, /matchmakingEnabled && row\.inquiry_available !== false/);
  assert.match(market, /directTradeEnabled \? row\.purchasable \?/);
  assert.match(detail, /matchmakingEnabled && product\.inquiry_available !== false/);
  assert.match(detail, /if \(!directTradeEnabled\) return/);
  assert.match(detail, /!product\.purchasable && !\(purchaseType === "holding" && holdingModeAvailable\)/);
});
