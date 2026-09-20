import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const html = fs.readFileSync(new URL("../public/info/index.html", import.meta.url), "utf8");
const script = fs.readFileSync(new URL("../public/info/app.js", import.meta.url), "utf8");
const styles = fs.readFileSync(new URL("../public/info/styles.css", import.meta.url), "utf8");
const showcaseStyles = fs.readFileSync(new URL("../public/info/showcase.css", import.meta.url), "utf8");
const nextConfig = fs.readFileSync(new URL("../next.config.ts", import.meta.url), "utf8");

test("/info is an isolated static page with production metadata and assets", () => {
  assert.match(nextConfig, /source: "\/info", destination: "\/info\/index\.html"/);
  assert.match(nextConfig, /connect-src 'none'/);
  assert.match(html, /<meta name="robots" content="index, follow" \/>/);
  assert.match(html, /<link rel="canonical" href="https:\/\/wod\.kai\.com\/info" \/>/);
  assert.match(html, /<title>算力星图算力资源信息<\/title>/);
  assert.match(html, /href="\/info\/styles\.css"/);
  assert.match(html, /href="\/info\/showcase\.css"/);
  assert.match(html, /src="\/info\/app\.js"/);
  assert.match(html, /src="\/info\/assets\/kai-logo\.svg"/);
  assert.ok(styles.length > 10_000);
  assert.ok(showcaseStyles.length > 5_000);
});

test("/info always uses the approved second layout without preview-port coupling", () => {
  assert.match(script, /^const showcaseMode = true;/);
  assert.doesNotMatch(html + script + styles + showcaseStyles, /9103|document\.baseURI|location\.port/);
  assert.match(script, /wod\.info\.requests\.v1/);
  assert.match(html, /企业算力资源信息服务/);
  assert.match(html, /沪ICP备2026046279号-1/);
  assert.match(html, /https:\/\/beian\.miit\.gov\.cn\//);
  assert.match(html, /联系我们：\+86 4001082026/);
  assert.doesNotMatch(html, /备案号待提供|联系方式将在正式资料确认后补充/);
});

test("/info remains browser-only and does not call application or external services", () => {
  const combined = html + script;
  assert.doesNotMatch(combined, /\bfetch\s*\(|XMLHttpRequest|axios|WebSocket|EventSource|sendBeacon/);
  assert.doesNotMatch(html, /<form[^>]+action=|https?:\/\/(?!wod\.kai\.com\/info|beian\.miit\.gov\.cn\/)/);
  assert.match(html, /connect-src 'none'/);
  assert.match(html, /form-action 'none'/);
});

test("/info ships all approved views, filters, resources, and local forms", () => {
  for (const view of ["resources", "manage", "schedule", "quote", "supplier", "about"]) {
    assert.match(html, new RegExp(`id="view-${view}"`));
  }
  assert.equal((html.match(/data-filter="/g) ?? []).length, 4);
  assert.equal((html.match(/<form class=/g) ?? []).length, 3);
  assert.equal((script.match(/^    id: "/gm) ?? []).length, 6);
  assert.match(script, /localStorage\.getItem\(storageKey\)/);
  assert.match(script, /localStorage\.setItem\(storageKey/);
  assert.match(script, /renderOrders\(\)/);
});

test("/info public source contains no preview placeholders or retired commercial wording", () => {
  const combined = html + script + styles + showcaseStyles;
  const retiredTerms = [
    "noindex",
    "XXXXXXXX",
    "备案信息将在核准后公示",
    "静态预览",
    "KAI Pricing",
    "订购",
    "订单",
    "购买",
    "可售",
    "供应商",
    "持有资产",
    "机柜托管",
    "结算",
    "公网接入",
    "认证数据中心",
  ];
  for (const term of retiredTerms) {
    assert.doesNotMatch(combined, new RegExp(term), `unexpected retired term: ${term}`);
  }
  assert.doesNotMatch(combined, /[—–]/);
});
