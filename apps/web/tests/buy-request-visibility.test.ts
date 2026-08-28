import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("supplier, buyer, and admin workspaces expose the closed matchmaking flow without leaking buyer identity", () => {
  const shell = fs.readFileSync(new URL("../components/product-shell.tsx", import.meta.url), "utf8");
  const workspace = fs.readFileSync(new URL("../components/mobile-buy-request-workspace.tsx", import.meta.url), "utf8");
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
  assert.match(workspace, /当前未创建资金订单，也未扣除卡时/);
  assert.match(adminApi, /\/admin\/buy-requests/);
  assert.match(adminApi, /\/credential\/release/);
  assert.match(admin, /审核通过/);
  assert.match(admin, /核验并放行/);
  assert.match(admin, /SSH 明文仅在凭据审核时按需读取/);
});
