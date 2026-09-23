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

test("every admin-system Chinese literal is translated directly or covered by the compatibility map", () => {
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
    const insideTranslationCall = (node: ts.Node) => {
      let parent = node.parent;
      while (parent && !ts.isSourceFile(parent)) {
        if (ts.isCallExpression(parent) && ts.isIdentifier(parent.expression) && parent.expression.text === "t") return true;
        parent = parent.parent;
      }
      return false;
    };
    const visit = (node: ts.Node) => {
      let text = "";
      if (ts.isJsxText(node) || ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) text = node.text;
      if (ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node)) text = node.text;
      text = text.replace(/\s+/g, " ").trim();
      if (/[\u3400-\u9fff]/.test(text) && !insideTranslationCall(node)) visibleChinese.add(text);
      ts.forEachChild(node, visit);
    };
    visit(file);
  }

  const missing = [...visibleChinese].filter((text) => !adminLegacyEnglish[text]);
  assert.deepEqual(missing, []);
});

test("supplier admission and shared admin controls render from explicit locale keys", () => {
  const supplierPage = fs.readFileSync(new URL("../app/supplier/apply/page.tsx", import.meta.url), "utf8");
  const supplierForm = fs.readFileSync(new URL("../components/supplier-application-form.tsx", import.meta.url), "utf8");
  const sourceFilter = fs.readFileSync(new URL("../components/admin-platform-filter.tsx", import.meta.url), "utf8");
  const pagination = fs.readFileSync(new URL("../components/admin-queue-pagination.tsx", import.meta.url), "utf8");
  const shell = fs.readFileSync(new URL("../components/product-shell.tsx", import.meta.url), "utf8");
  const payments = fs.readFileSync(new URL("../components/admin-payment-operations-workspace.tsx", import.meta.url), "utf8");

  for (const key of [
    "supplier.apply.title",
    "supplier.apply.description",
    "supplier.apply.formTitle",
    "supplier.apply.formDescriptionLink",
  ]) assert.match(supplierPage, new RegExp(key.replaceAll(".", "\\.")));
  for (const key of [
    "supplier.apply.field.company",
    "supplier.apply.field.contact",
    "supplier.apply.field.phone",
    "supplier.apply.field.region",
    "supplier.apply.field.description",
    "supplier.apply.submit",
  ]) assert.match(supplierForm, new RegExp(key.replaceAll(".", "\\.")));

  assert.match(sourceFilter, /t\("admin\.filter\.allSources"/);
  assert.match(pagination, /t\("admin\.pagination\.summary"/);
  assert.match(shell, /KAI Compute Cloud Administrator/);
  assert.match(payments, /t\("admin\.payment\.boundaryPrefix"/);
  assert.match(payments, /<\/Link> \{t\("admin\.payment\.boundarySuffix"/);
  assert.doesNotMatch(payments, /<\/Link>只退回/);
});

test("explicit admin translations have an English key or a mapped English fallback", () => {
  const localeSource = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");
  const englishKeys = new Set([...localeSource.matchAll(/^\s*"([^"]+)":/gm)].map((match) => match[1]));
  const components = [
    "admin-buy-request-workspace.tsx",
    "admin-platform-audit-workspace.tsx",
    "supplier-review.tsx",
    "admin-dispute-workspace.tsx",
    "admin-notification-workspace.tsx",
    "admin-payment-operations-workspace.tsx",
    "comment-moderation.tsx",
    "admin-platform-filter.tsx",
    "admin-queue-pagination.tsx",
  ];
  const missing: string[] = [];

  for (const component of components) {
    const url = new URL(`../components/${component}`, import.meta.url);
    const source = fs.readFileSync(url, "utf8");
    const file = ts.createSourceFile(url.pathname, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const visit = (node: ts.Node) => {
      if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === "t") {
        const [keyNode, fallbackNode] = node.arguments;
        if (ts.isStringLiteral(keyNode) && ts.isStringLiteral(fallbackNode) && /[\u3400-\u9fff]/.test(fallbackNode.text)) {
          if (!englishKeys.has(keyNode.text) && !adminLegacyEnglish[fallbackNode.text]) {
            missing.push(`${component}: ${keyNode.text}`);
          }
        }
      }
      ts.forEachChild(node, visit);
    };
    visit(file);
  }

  assert.deepEqual(missing, []);
});
