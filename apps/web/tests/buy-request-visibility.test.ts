import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("supplier, buyer, and admin workspaces expose the closed matchmaking flow without leaking buyer identity", () => {
  const shell = fs.readFileSync(new URL("../components/product-shell.tsx", import.meta.url), "utf8");
  const workspace = fs.readFileSync(new URL("../components/mobile-buy-request-workspace.tsx", import.meta.url), "utf8");
  const requestApi = fs.readFileSync(new URL("../lib/mobile-buy-request-api.ts", import.meta.url), "utf8");
  const localeRoot = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");
  const supplierPage = fs.readFileSync(new URL("../app/supplier/requests/page.tsx", import.meta.url), "utf8");
  const adminApi = fs.readFileSync(new URL("../lib/admin-audit-api.ts", import.meta.url), "utf8");
  const admin = fs.readFileSync(new URL("../components/admin-buy-request-workspace.tsx", import.meta.url), "utf8");

  assert.match(shell, /href: "\/supplier\/requests"/);
  assert.match(shell, /href: "\/admin\/requests"/);
  assert.match(workspace, /detail\.request\.is_own/);
  assert.match(workspace, /不能给自己的需求/);
  assert.match(workspace, /匿名需求 #\$\{row\.id\}/);
  assert.doesNotMatch(workspace, /row\.buyer_name/);
  assert.doesNotMatch(workspace, /detail\.request\.(?:contact|phone|buyer_name)/);
  assert.match(workspace, /counterMobileBuyQuote/);
  assert.match(workspace, /confirmMobileBuyRequestDeal/);
  assert.match(workspace, /submitMobileBuyRequestCredential/);
  assert.match(workspace, /confirmMobileBuyRequestDelivery/);
  assert.match(workspace, /全部需求/);
  assert.match(workspace, /我的报价需求/);
  assert.match(workspace, /sellerScope === "quoted"/);
  assert.match(workspace, /coordination_requested: "平台协调中"/);
  assert.match(workspace, /quote_submitted: "商家已提交方案"/);
  assert.match(workspace, /timelineEventLabel\(event\)/);
  assert.match(workspace, /view === "seller" && !detail\?\.request\.is_own/);
  assert.match(requestApi, /quoted_only=true/);
  for (const [source, translated] of [
    ["需求显示范围", "Request display scope"],
    ["显示范围", "Display scope"],
    ["全部需求", "All requests"],
    ["我的报价", "My quotes"],
    ["我的报价需求", "My quoted requests"],
    ["暂无报价记录", "No quote history"],
  ]) {
    assert.match(localeRoot, new RegExp(`"${source}": "${translated}"`));
  }
  assert.match(supplierPage, /scope === "quoted" \? "quoted" : "all"/);
  assert.match(workspace, /当前未创建资金订单，也未扣除卡时/);
  assert.match(adminApi, /\/admin\/buy-requests/);
  assert.match(adminApi, /\/credential\/release/);
  assert.match(admin, /审核通过/);
  assert.match(admin, /核验并放行/);
  assert.match(admin, /coordination_requested: "平台协调中"/);
  assert.match(admin, /declined: "未选中"/);
  assert.match(admin, /quote_submitted: "商家已提交方案"/);
  assert.match(admin, /statusLabel\(row\.deal\?\.status \|\| row\.status\)/);
  assert.match(admin, /statusLabel\(detail\.deal\?\.status \|\| detail\.request\.status\)/);
  assert.match(admin, /statusLabel\(quote\.status\)/);
  assert.match(admin, /statusLabel\(detail\.deal\.status\)/);
  assert.match(admin, /timelineEventLabel\(event\)/);
  assert.match(admin, /\|\| "状态待确认"/);
  assert.doesNotMatch(admin, /statusLabels\[row\.deal\?\.status/);
  assert.doesNotMatch(admin, /statusLabels\[detail\.deal\?\.status/);
  assert.doesNotMatch(admin, /statusLabels\[quote\.status\] \|\| quote\.status/);
  assert.doesNotMatch(admin, /statusLabels\[detail\.deal\.status\] \|\| detail\.deal\.status/);
  assert.doesNotMatch(admin, /event\.label \|\| statusLabels/);
  assert.match(admin, /SSH 明文仅在凭据审核时按需读取/);
});

test("administrator request filters cover every persisted workflow stage", () => {
  const admin = fs.readFileSync(new URL("../components/admin-buy-request-workspace.tsx", import.meta.url), "utf8");
  const adminApi = fs.readFileSync(new URL("../lib/admin-audit-api.ts", import.meta.url), "utf8");
  const filterSource = admin.match(/const statusFilterGroups = \[([\s\S]*?)\] as const;/)?.[1];

  assert.ok(filterSource, "status filter configuration must remain explicit and testable");
  assert.deepEqual(
    [...filterSource.matchAll(/"([a-z_]+)"/g)].map((match) => match[1]),
    [
      "platform_review",
      "credential_submitted",
      "delivery_disputed",
      "published",
      "quoting",
      "buyer_selected",
      "credential_pending",
      "credential_rejected",
      "credential_released",
      "quote_selected",
      "processing",
      "completed",
      "expired",
      "closed",
      "rejected",
    ],
  );
  assert.match(filterSource, /需要平台处理/);
  assert.match(filterSource, /撮合进行中/);
  assert.match(filterSource, /已结束/);
  assert.match(admin, /group\.values\.map\(\(value\) => <option key=\{value\} value=\{value\}>\{statusLabel\(value\)\}<\/option>/);
  assert.match(adminApi, /params\.set\("status", input\.status\.trim\(\)\)/);
});
