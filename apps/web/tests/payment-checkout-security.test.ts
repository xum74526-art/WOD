import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { qixiangCheckoutHref } from "../lib/payment-checkout-navigation.ts";
import {
  allowedPaymentCheckoutRedirect,
  paymentCheckoutAllowedHosts,
  paymentCheckoutClientIp,
} from "../lib/server/payment-checkout-policy.ts";

test("wallet checkout navigation accepts only same-origin canonical Qixiang tokens", () => {
  const origin = "https://wod.kai.com";
  const firstToken = "a".repeat(43);
  const secondToken = "b".repeat(43);
  assert.equal(
    qixiangCheckoutHref(`/api/payments/qixiang/checkout/${firstToken}`, origin),
    `/api/v1/canonical/payments/qixiang/checkout/${firstToken}`,
  );
  assert.equal(
    qixiangCheckoutHref(`https://wod.kai.com/api/v1/canonical/payments/qixiang/checkout/${secondToken}`, origin),
    `/api/v1/canonical/payments/qixiang/checkout/${secondToken}`,
  );
  for (const unsafe of [
    "javascript:alert(1)",
    "https://evil.example/api/payments/qixiang/checkout/token",
    "//evil.example/api/payments/qixiang/checkout/token",
    "/api/payments/mapay/checkout/token",
    "/api/payments/qixiang/checkout/token?next=https://evil.example",
    "/api/payments/qixiang/checkout/token#fragment",
    "/account/wallet",
  ]) {
    assert.equal(qixiangCheckoutHref(unsafe, origin), null, unsafe);
  }
});

test("BFF checkout redirects require HTTPS and an exact allowlisted host", () => {
  const hosts = paymentCheckoutAllowedHosts({ PAYMENT_CHECKOUT_ALLOWED_HOSTS: "cashier.example.test, invalid host" });
  assert.ok(hosts.has("api.payqixiang.cn"));
  assert.ok(hosts.has("cashier.example.test"));
  assert.equal(allowedPaymentCheckoutRedirect("https://cashier.example.test/pay?id=1", hosts)?.hostname, "cashier.example.test");
  for (const unsafe of [
    "http://cashier.example.test/pay",
    "https://cashier.example.test:444/pay",
    "https://user:pass@cashier.example.test/pay",
    "https://evil.cashier.example.test/pay",
    "https://cashier.example.test.evil.example/pay",
    "/relative/pay",
  ]) {
    assert.equal(allowedPaymentCheckoutRedirect(unsafe, hosts), null, unsafe);
  }
});

test("BFF forwards only Nginx-derived valid client IPs to checkout creation", () => {
  assert.equal(paymentCheckoutClientIp(new Headers({ "x-real-ip": "203.0.113.25" })), "203.0.113.25");
  assert.equal(paymentCheckoutClientIp(new Headers({ "x-real-ip": "2001:db8::25" })), "2001:db8::25");
  for (const unsafe of ["", "203.0.113.25, 10.0.0.1", "unknown", "203.0.113.999"] ) {
    assert.equal(paymentCheckoutClientIp(new Headers({ "x-real-ip": unsafe })), null);
  }
  const adapter = readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");
  const proxy = adapter.slice(adapter.indexOf("async function proxyCheckout"), adapter.indexOf("function product", adapter.indexOf("async function proxyCheckout")));
  assert.match(proxy, /paymentCheckoutClientIp\(request\.headers\)/);
  assert.match(proxy, /headers\.set\("X-Real-IP", clientIp\)/);
});

test("the BFF is redirect-only and keeps the legacy Mapay route fail-closed", () => {
  const adapter = readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");
  const proxy = adapter.slice(adapter.indexOf("async function proxyCheckout"), adapter.indexOf("function product", adapter.indexOf("async function proxyCheckout")));

  assert.match(proxy, /provider !== "qixiang"/);
  assert.match(proxy, /legacy_checkout_disabled/);
  assert.match(proxy, /response\.status === 303/);
  assert.match(proxy, /allowedPaymentCheckoutRedirect\(location, paymentCheckoutAllowedHosts\(\)\)/);
  assert.doesNotMatch(proxy, /response\.body|text\/html/);
});

test("legacy payment pages redirect and the Qixiang return page never trusts query state", () => {
  const oldPayment = readFileSync(new URL("../app/payment/[paymentNo]/page.tsx", import.meta.url), "utf8");
  const oldLeases = readFileSync(new URL("../app/account/leases/page.tsx", import.meta.url), "utf8");
  const oldSupplierLeases = readFileSync(new URL("../app/supplier/leases/page.tsx", import.meta.url), "utf8");
  const paymentReturn = readFileSync(new URL("../app/payment/qixiang/return/page.tsx", import.meta.url), "utf8");

  assert.match(oldPayment, /redirect\("\/account\/wallet"\)/);
  assert.match(oldLeases, /redirect\("\/account\/orders"\)/);
  assert.match(oldSupplierLeases, /redirect\("\/supplier\/orders"\)/);
  assert.match(paymentReturn, /router\.replace\("\/account\/wallet"\)/);
  assert.match(paymentReturn, /只以服务端验签和钱包入账记录为准/);
  assert.doesNotMatch(paymentReturn, /useSearchParams|searchParams|支付成功/);
});

test("Ping++ runtime code and dependency are removed", () => {
  const packageJson = readFileSync(new URL("../package.json", import.meta.url), "utf8");
  const lock = readFileSync(new URL("../package-lock.json", import.meta.url), "utf8");
  const commerce = readFileSync(new URL("../lib/commerce-api.ts", import.meta.url), "utf8");
  const mobileBusiness = readFileSync(new URL("../lib/mobile-business-api.ts", import.meta.url), "utf8");

  assert.doesNotMatch(packageJson, /pingpp-js/);
  assert.doesNotMatch(lock, /pingpp-js/);
  assert.doesNotMatch(`${commerce}\n${mobileBusiness}`, /PaymentCredential|payments\/intents|\/credential|\/reconcile/);
});

test("supplier withdrawals and account notices use the specific withdrawal and recharge capabilities", () => {
  const supplier = readFileSync(new URL("../components/mobile-supplier-operations.tsx", import.meta.url), "utf8");
  const account = readFileSync(new URL("../components/account-dashboard.tsx", import.meta.url), "utf8");
  const adapter = readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");

  assert.match(supplier, /capabilities\.withdraw_enabled === true/);
  assert.match(supplier, /href="\/account\/wallet">前往钱包申请提现/);
  assert.doesNotMatch(supplier, /!wallet\?\.payment_service_enabled/);
  assert.match(account, /!summary\.services\.recharge/);
  assert.match(account, /!summary\.services\.withdraw/);
  assert.match(adapter, /recharge: Boolean\(wallet\.recharge_service_enabled\)/);
  assert.match(adapter, /withdraw: Boolean\(wallet\.withdraw_service_enabled\)/);
});
