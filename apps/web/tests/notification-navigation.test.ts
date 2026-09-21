import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { notificationActionPath } from "../lib/notification-navigation.ts";

test("notification actions map the exact mobile allowlist onto Web routes", () => {
  assert.equal(notificationActionPath("/pages/order/detail?id=7"), "/account/orders?order=7");
  assert.equal(notificationActionPath("/pages/order/detail?id=9007199254740991"), "/account/orders?order=9007199254740991");
  assert.equal(notificationActionPath("/pages/supplier/orders"), "/supplier/orders");
  assert.equal(notificationActionPath("/pages/asset/detail?id=23"), "/account/assets/23");
  assert.equal(notificationActionPath("/pages/revenue/index"), "/account/revenue");
  assert.equal(notificationActionPath("/pages/wallet/index"), "/account/wallet");
  assert.equal(notificationActionPath("/pages/notifications/index"), "/account/notifications");
  assert.equal(notificationActionPath("/pages/market/index"), "/market");
  assert.equal(notificationActionPath("/pages/community/index"), "/community");
  assert.equal(notificationActionPath("/pages/settings/index"), "/account/settings");
});

test("notification actions reject malformed IDs and non-exact query strings", () => {
  for (const value of [
    "/pages/order/detail",
    "/pages/order/detail?",
    "/pages/order/detail?id=",
    "/pages/order/detail?id=0",
    "/pages/order/detail?id=-1",
    "/pages/order/detail?id=1.5",
    "/pages/order/detail?id=01",
    "/pages/order/detail?id=+1",
    "/pages/order/detail?id=1e2",
    "/pages/order/detail?id=9007199254740992",
    "/pages/order/detail?id=1&id=2",
    "/pages/order/detail?id=1&next=/account/wallet",
    "/pages/order/detail?next=/account/wallet&id=1",
    "/pages/asset/detail",
    "/pages/asset/detail?id=0",
    "/pages/asset/detail?id=2.5",
    "/pages/asset/detail?id=3&extra=1",
    "/pages/supplier/orders?scope=all",
    "/pages/revenue/index?tab=all",
    "/pages/wallet/index?",
  ]) {
    assert.equal(notificationActionPath(value), null, `must reject ${JSON.stringify(value)}`);
  }
});

test("notification actions reject browser-normalization and encoded bypasses", () => {
  for (const value of [
    null,
    undefined,
    7,
    "",
    "pages/wallet/index",
    "https://evil.example/pages/wallet/index",
    "//evil.example/pages/wallet/index",
    "/\\evil.example/pages/wallet/index",
    "\\\\evil.example\\pages\\wallet\\index",
    "/pages\\wallet\\index",
    "/pages/wallet/index#balance",
    "/pages/wallet/index\n",
    "/pages/wallet/index\u0000",
    "/pages/order/detail?id=1\n",
    "/pages/order/detail?id=1\r",
    "/pages/order/detail?id=1\t",
    "/pages/order/detail?id=1\u2028",
    "/pages/order/detail?id=1\u2029",
    "/pages/asset/detail?id=1\u007f",
    "/pages/%2e%2e/wallet/index",
    "/pages/order/%2e%2e/wallet/index",
    "/pages/order/detail%3Fid%3D1",
    "/pages/order/detail?id=%31",
    "/pages/order/detail?id=1%26next%3D%2Faccount%2Fwallet",
    "/pages%2Forder%2Fdetail?id=1",
    "/pages/order/detail/../detail?id=1",
    "/pages//order/detail?id=1",
    "/pages/unknown/index",
    "/account/wallet",
  ]) {
    assert.equal(notificationActionPath(value), null, `must reject ${JSON.stringify(value)}`);
  }
});

test("the notice adapter always applies the shared notification mapper", () => {
  const adapter = readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");

  assert.match(adapter, /import \{ notificationActionPath \} from "@\/lib\/notification-navigation"/);
  assert.match(adapter, /title_en: text\(item\.title_en\) \|\| null/);
  assert.match(adapter, /body_en: text\(item\.content_en\) \|\| null/);
  assert.match(adapter, /action_path: notificationActionPath\(item\.action_url\)/);
  assert.doesNotMatch(adapter, /action_path: text\(item\.action_url\)/);
});
