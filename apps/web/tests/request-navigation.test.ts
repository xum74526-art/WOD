import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { legacyRequestCreateHref } from "../lib/request-navigation.ts";

test("legacy request creation links preserve only supported prefill values", () => {
  assert.equal(
    legacyRequestCreateHref({
      gpu_model: "H100 80GB",
      quantity: "8",
      product_id: "not-a-number",
      supplier_id: "-3",
      region: ["CN-SH", "US-WEST"],
      return_to: "https://evil.example",
      next: "//evil.example",
      url: "javascript:alert(1)",
    }),
    "/account/requests?create=1&gpu_model=H100+80GB&quantity=8&region=CN-SH",
  );
  assert.equal(
    legacyRequestCreateHref({ create: "0", product_id: "7", gpu_hours: ["24", "48"] }),
    "/account/requests?create=1&product_id=7&gpu_hours=24",
  );
});

test("legacy request pages no longer render clients backed by removed public APIs", () => {
  const listPage = readFileSync(new URL("../app/requests/page.tsx", import.meta.url), "utf8");
  const detailPage = readFileSync(new URL("../app/requests/[request_no]/page.tsx", import.meta.url), "utf8");
  const createPage = readFileSync(new URL("../app/requests/new/page.tsx", import.meta.url), "utf8");
  const commerceApi = readFileSync(new URL("../lib/commerce-api.ts", import.meta.url), "utf8");

  assert.match(listPage, /redirect\("\/account\/requests"\)/);
  assert.match(detailPage, /redirect\("\/account\/requests"\)/);
  assert.match(createPage, /legacyRequestCreateHref\(await searchParams\)/);
  assert.doesNotMatch(listPage, /RequestMarketplace/);
  assert.doesNotMatch(detailPage, /PublicRequestDetail/);
  assert.doesNotMatch(commerceApi, /\/api\/v1\/(?:public|account)\/buy-requests/);
});

test("legacy supplier quote ledger opens the canonical supplier request workspace", () => {
  const quotePage = readFileSync(new URL("../app/supplier/quotes/page.tsx", import.meta.url), "utf8");
  const commerceApi = readFileSync(new URL("../lib/commerce-api.ts", import.meta.url), "utf8");

  assert.match(quotePage, /redirect\("\/supplier\/requests\?scope=quoted"\)/);
  assert.doesNotMatch(quotePage, /components\/supplier-quotes|<SupplierQuotes/);
  assert.doesNotMatch(commerceApi, /export function listSupplierQuotes/);
});
