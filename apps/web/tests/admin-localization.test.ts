import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import * as ts from "typescript";

import { adminLegacyEnglish } from "../lib/admin-legacy-english.ts";
import { localizeSupplierName } from "../lib/market-localization.ts";

test("English public market uses an English brand and supplier label", () => {
  const locale = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");
  const market = fs.readFileSync(new URL("../components/merchant-resource-market.tsx", import.meta.url), "utf8");
  const brand = fs.readFileSync(new URL("../components/brand.tsx", import.meta.url), "utf8");

  assert.equal(localizeSupplierName("KAI星算自营", "en"), "KAI Star Self-operated");
  assert.match(locale, /replaceAll\("KAI星算", "KAI Star"\)/);
  assert.match(market, /locale === "en" \? "KAI COMPUTE SELF-OPERATED"/);
  assert.match(brand, /locale === "en" \? "KAI Star" : "KAI星算"/);
});

test("admin overview uses component translations and legacy queues have English coverage", () => {
  const dashboard = fs.readFileSync(new URL("../components/admin-dashboard.tsx", import.meta.url), "utf8");
  const locale = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

  assert.match(dashboard, /"use client"/);
  assert.match(dashboard, /useI18n/);
  assert.match(dashboard, /t\("admin\.dashboard\.title"/);
  assert.match(dashboard, /t\(titleKey, title\)/);
  assert.match(locale, /adminLegacyEnglish\[trimmed\]/);

  for (const chinese of [
    "撮合交易管理",
    "端口数据",
    "实名认证审核",
    "商家准入审核",
    "订单争议仲裁",
    "发布新消息",
    "充值与人民币原路退款",
    "银行卡登记复核",
    "提现结算",
    "社区举报与内容治理",
  ]) {
    assert.ok(adminLegacyEnglish[chinese], `missing English admin copy for ${chinese}`);
    assert.doesNotMatch(adminLegacyEnglish[chinese], /[\u3400-\u9fff]/);
  }
});

test("every static Chinese admin label has an English compatibility translation", () => {
  const components = [
    "admin-dashboard.tsx",
    "admin-buy-request-workspace.tsx",
    "admin-platform-audit-workspace.tsx",
    "admin-kyc-workspace.tsx",
    "supplier-review.tsx",
    "admin-dispute-workspace.tsx",
    "admin-notification-workspace.tsx",
    "admin-payment-operations-workspace.tsx",
    "admin-bank-card-workspace.tsx",
    "admin-withdrawal-workspace.tsx",
    "comment-moderation.tsx",
  ];
  const visibleChinese = new Set<string>();

  for (const component of components) {
    const url = new URL(`../components/${component}`, import.meta.url);
    const source = fs.readFileSync(url, "utf8");
    const file = ts.createSourceFile(url.pathname, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const visit = (node: ts.Node) => {
      if (ts.isJsxText(node)) {
        const text = node.text.trim();
        if (/[\u3400-\u9fff]/.test(text)) visibleChinese.add(text);
      }
      if (ts.isStringLiteral(node) && ts.isJsxAttribute(node.parent) && /[\u3400-\u9fff]/.test(node.text)) {
        visibleChinese.add(node.text);
      }
      ts.forEachChild(node, visit);
    };
    visit(file);
  }

  const missing = [...visibleChinese].filter((text) => !adminLegacyEnglish[text]);
  assert.deepEqual(missing, []);
});
