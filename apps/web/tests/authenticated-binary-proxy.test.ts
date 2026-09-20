import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { proxyAuthenticatedBinary } from "../lib/server/authenticated-binary-proxy.ts";

test("withdrawal receipt route uses its dedicated binary proxy before generic JSON handling", () => {
  const adapter = fs.readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");
  const routeIndex = adapter.indexOf("const withdrawalReceipt = path.match(");
  const genericJsonIndex = adapter.indexOf('if (path.startsWith("canonical/"))');
  const route = adapter.slice(routeIndex, genericJsonIndex);
  const proxyIndex = adapter.indexOf("async function proxyWithdrawalReceipt(");
  const nextProxyIndex = adapter.indexOf("async function proxyCheckout(", proxyIndex);
  const proxy = adapter.slice(proxyIndex, nextProxyIndex);

  assert.ok(routeIndex >= 0);
  assert.ok(genericJsonIndex > routeIndex);
  assert.match(route, /canonical\\\/finance\\\/withdrawals\\\/\(\[1-9\]\\d\*\)\\\/receipt/);
  assert.match(route, /request\.method === "GET"/);
  assert.match(route, /proxyWithdrawalReceipt\(request, withdrawalReceipt\[1\]\)/);
  assert.match(proxy, /request\.cookies\.get\(TOKEN_COOKIE\)\?\.value/);
  assert.match(proxy, /if \(!token\) return apiError\("未登录", 401\)/);
  assert.match(proxy, /\/api\/finance\/withdrawals\/\$\{orderId\}\/receipt/);
  assert.match(proxy, /token,\s*accept: PAYOUT_RECEIPT_ACCEPT/);
  assert.match(proxy, /allowedContentTypes: PAYOUT_RECEIPT_MIME_TYPES/);
  assert.match(proxy, /downloadId: Number\(orderId\)/);
});

test("authenticated binary proxy forwards the bearer and streams receipt bytes with safe headers", async () => {
  const bytes = new TextEncoder().encode("%PDF-1.7\nreceipt-body\n%%EOF");
  let calledUrl = "";
  let calledInit: RequestInit | undefined;
  const result = await proxyAuthenticatedBinary({
    url: "https://api.example.test/api/finance/withdrawals/42/receipt",
    token: "http-only-cookie-token",
    accept: "image/jpeg,image/png,application/pdf",
    allowedContentTypes: ["image/jpeg", "image/png", "application/pdf"],
    downloadId: 42,
    fetcher: async (url, init) => {
      calledUrl = String(url);
      calledInit = init;
      return new Response(bytes, {
        headers: {
          "Content-Type": "application/pdf",
          "Content-Length": String(bytes.byteLength),
          "Content-Disposition": 'attachment; filename="untrusted-upstream-name.pdf"',
        },
      });
    },
  });

  assert.equal(calledUrl, "https://api.example.test/api/finance/withdrawals/42/receipt");
  assert.equal(new Headers(calledInit?.headers).get("authorization"), "Bearer http-only-cookie-token");
  assert.equal(new Headers(calledInit?.headers).get("accept"), "image/jpeg,image/png,application/pdf");
  assert.equal(calledInit?.cache, "no-store");
  assert.equal(calledInit?.redirect, "manual");
  assert.equal(result.ok, true);
  if (!result.ok) return;

  assert.deepEqual(new Uint8Array(await result.response.arrayBuffer()), bytes);
  assert.equal(result.response.headers.get("content-type"), "application/pdf");
  assert.equal(result.response.headers.get("content-length"), null);
  assert.equal(result.response.headers.get("content-disposition"), 'attachment; filename="withdrawal-receipt-42.pdf"');
  assert.equal(result.response.headers.get("x-content-type-options"), "nosniff");
  assert.equal(result.response.headers.get("cache-control"), "private, no-store, max-age=0");
  assert.equal(result.response.headers.get("pragma"), "no-cache");
  assert.equal(result.response.headers.get("referrer-policy"), "no-referrer");
  assert.equal(result.response.headers.get("content-security-policy"), "default-src 'none'; sandbox");
  assert.equal(result.response.headers.get("cross-origin-resource-policy"), "same-origin");
});

test("binary proxy never parses an upstream authorization error as a file", async () => {
  let cancelled = false;
  const result = await proxyAuthenticatedBinary({
    url: "https://api.example.test/api/finance/withdrawals/42/receipt",
    token: "expired-token",
    accept: "application/pdf",
    allowedContentTypes: ["application/pdf"],
    downloadId: 42,
    fetcher: async () => new Response(new ReadableStream({ cancel() { cancelled = true; } }), { status: 403 }),
  });

  assert.deepEqual(result, { ok: false, status: 403, unavailable: false });
  assert.equal(cancelled, true);
});

test("binary proxy rejects an unexpected upstream media type", async () => {
  let cancelled = false;
  const result = await proxyAuthenticatedBinary({
    url: "https://api.example.test/api/finance/withdrawals/42/receipt",
    token: "admin-token",
    accept: "image/jpeg,image/png,application/pdf",
    allowedContentTypes: ["image/jpeg", "image/png", "application/pdf"],
    downloadId: 42,
    fetcher: async () => new Response(new ReadableStream({ cancel() { cancelled = true; } }), {
      headers: { "Content-Type": "text/html" },
    }),
  });

  assert.deepEqual(result, { ok: false, status: 502, unavailable: false });
  assert.equal(cancelled, true);
});

test("binary proxy rejects redirects, partial responses, and empty successes without exposing upstream headers", async () => {
  let redirectCancelled = false;
  const redirect = await proxyAuthenticatedBinary({
    url: "https://api.example.test/api/finance/withdrawals/42/receipt",
    token: "admin-token",
    accept: "application/pdf",
    allowedContentTypes: ["application/pdf"],
    downloadId: 42,
    fetcher: async () => new Response(new ReadableStream({ cancel() { redirectCancelled = true; } }), {
      status: 302,
      headers: { Location: "https://attacker.example/receipt" },
    }),
  });
  let partialCancelled = false;
  const partial = await proxyAuthenticatedBinary({
    url: "https://api.example.test/api/finance/withdrawals/42/receipt",
    token: "admin-token",
    accept: "application/pdf",
    allowedContentTypes: ["application/pdf"],
    downloadId: 42,
    fetcher: async () => new Response(new ReadableStream({ cancel() { partialCancelled = true; } }), {
      status: 206,
      headers: { "Content-Type": "application/pdf", "Content-Range": "bytes 0-99/200" },
    }),
  });
  const empty = await proxyAuthenticatedBinary({
    url: "https://api.example.test/api/finance/withdrawals/42/receipt",
    token: "admin-token",
    accept: "application/pdf",
    allowedContentTypes: ["application/pdf"],
    downloadId: 42,
    fetcher: async () => new Response(null, { status: 200, headers: { "Content-Type": "application/pdf" } }),
  });
  const noContent = await proxyAuthenticatedBinary({
    url: "https://api.example.test/api/finance/withdrawals/42/receipt",
    token: "admin-token",
    accept: "application/pdf",
    allowedContentTypes: ["application/pdf"],
    downloadId: 42,
    fetcher: async () => new Response(null, { status: 204 }),
  });

  assert.deepEqual(redirect, { ok: false, status: 502, unavailable: false });
  assert.equal(redirectCancelled, true);
  assert.deepEqual(partial, { ok: false, status: 502, unavailable: false });
  assert.equal(partialCancelled, true);
  assert.deepEqual(empty, { ok: false, status: 502, unavailable: false });
  assert.deepEqual(noContent, { ok: false, status: 502, unavailable: false });
});

test("binary proxy ignores hostile upstream disposition and derives a safe extension for every allowed type", async () => {
  for (const [contentType, extension] of [["image/jpeg", "jpg"], ["image/png", "png"], ["application/pdf", "pdf"]] as const) {
    const result = await proxyAuthenticatedBinary({
      url: "https://api.example.test/api/finance/withdrawals/42/receipt",
      token: "admin-token",
      accept: "image/jpeg,image/png,application/pdf",
      allowedContentTypes: ["image/jpeg", "image/png", "application/pdf"],
      downloadId: 42,
      fetcher: async () => new Response("receipt", {
        headers: {
          "Content-Type": contentType,
          "Content-Disposition": 'attachment; filename="bad\\r\\nname.html"',
        },
      }),
    });

    assert.equal(result.ok, true);
    if (result.ok) assert.equal(result.response.headers.get("content-disposition"), `attachment; filename="withdrawal-receipt-42.${extension}"`);
  }
});

test("binary proxy rejects an unsafe download id and cancels the upstream body", async () => {
  let cancelled = false;
  const result = await proxyAuthenticatedBinary({
    url: "https://api.example.test/api/finance/withdrawals/42/receipt",
    token: "admin-token",
    accept: "application/pdf",
    allowedContentTypes: ["application/pdf"],
    downloadId: Number.NaN,
    fetcher: async () => new Response(new ReadableStream({ cancel() { cancelled = true; } }), {
      headers: { "Content-Type": "application/pdf" },
    }),
  });

  assert.deepEqual(result, { ok: false, status: 502, unavailable: false });
  assert.equal(cancelled, true);
});
