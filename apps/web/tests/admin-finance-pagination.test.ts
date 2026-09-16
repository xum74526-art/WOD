import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  ADMIN_QUEUE_PAGE_SIZE,
  adminQueuePageCount,
  adminQueuePageRange,
} from "../lib/admin-queue-pagination.ts";

test("admin finance pagination calculates stable page counts and visible ranges", () => {
  assert.equal(ADMIN_QUEUE_PAGE_SIZE, 20);
  assert.equal(adminQueuePageCount(0), 1);
  assert.equal(adminQueuePageCount(20), 1);
  assert.equal(adminQueuePageCount(21), 2);
  assert.deepEqual(adminQueuePageRange(1, 21), { first: 1, last: 20 });
  assert.deepEqual(adminQueuePageRange(2, 21), { first: 21, last: 21 });
  assert.deepEqual(adminQueuePageRange(99, 21), { first: 21, last: 21 });
  assert.deepEqual(adminQueuePageRange(1, 0), { first: 0, last: 0 });
});

test("finance list clients send caller-selected pages instead of truncating at the first 100 rows", () => {
  const api = fs.readFileSync(new URL("../lib/mobile-finance-api.ts", import.meta.url), "utf8");

  assert.match(api, /type FinancePage<T> = \{ total: number; page: number; page_size: number; items: T\[\] \}/);
  assert.match(api, /page: String\(page\), page_size: String\(pageSize\)/);
  assert.match(api, /boundedPositiveInteger\(input\.pageSize, 20, 100\)/);
  assert.match(api, /listFinanceBankCards\(input: FinanceListInput/);
  assert.match(api, /listFinanceVerifications\(input: FinanceListInput/);
  assert.match(api, /listFinanceWithdrawals\(input: FinanceListInput/);
  assert.doesNotMatch(api, /page:\s*"1",\s*page_size:\s*"100"/);
});

test("all three finance admin queues expose total-aware previous and next page navigation", () => {
  const cases = [
    ["../components/admin-kyc-workspace.tsx", "listFinanceVerifications"],
    ["../components/admin-bank-card-workspace.tsx", "listFinanceBankCards"],
    ["../components/admin-withdrawal-workspace.tsx", "listFinanceWithdrawals"],
  ] as const;

  for (const [path, listFunction] of cases) {
    const source = fs.readFileSync(new URL(path, import.meta.url), "utf8");
    assert.match(source, /const \[page, setPage\] = useState\(1\)/, `${path} must keep the active page`);
    assert.match(source, /const \[total, setTotal\] = useState\(0\)/, `${path} must keep the filtered total`);
    assert.match(source, new RegExp(`${listFunction}\\(\\{[\\s\\S]*?page: query\\.page,[\\s\\S]*?pageSize: ADMIN_QUEUE_PAGE_SIZE`));
    assert.match(source, /if \(query\.page > pageCount\) \{[\s\S]*?setPage\(pageCount\)/, `${path} must retreat from an invalid last page`);
    assert.match(source, /function changeStatus\([\s\S]*?setStatus\(value\); setPage\(1\); \}/, `${path} must reset status filters to page one`);
    assert.match(source, /function changePlatform\([\s\S]*?setPlatform\(value\); setPage\(1\); \}/, `${path} must reset platform filters to page one`);
    assert.match(source, /const requestSequence = useRef\(0\)/, `${path} must reject stale responses`);
    assert.match(source, /query\.status === queryRef\.current\.status/);
    assert.match(source, /if \(!isCurrentQuery\(\)\) return/);
    assert.match(source, /<AdminQueuePagination page=\{page\} total=\{total\} loading=\{loading\} onPageChange=/);
  }
});

test("withdrawal navigation discards an open payment form and its selected receipt", () => {
  const source = fs.readFileSync(new URL("../components/admin-withdrawal-workspace.tsx", import.meta.url), "utf8");
  const resets = source.match(/setPaying\(null\); setReceipt\(null\);/g) ?? [];

  assert.ok(resets.length >= 3);
  assert.match(source, /function changePage\(value: number\) \{[\s\S]*?setPaying\(null\); setReceipt\(null\); setPage\(value\); \}/);
  assert.match(source, /onPageChange=\{changePage\}/);
});

test("shared queue pagination disables invalid navigation and reports the filtered total", () => {
  const component = fs.readFileSync(new URL("../components/admin-queue-pagination.tsx", import.meta.url), "utf8");

  assert.match(component, /disabled=\{loading \|\| page <= 1\}/);
  assert.match(component, /disabled=\{loading \|\| page >= pageCount\}/);
  assert.match(component, /第 \{page\} \/ \{pageCount\} 页/);
  assert.match(component, /共 \{total\} 条/);
  assert.match(component, /aria-live="polite"/);
});
