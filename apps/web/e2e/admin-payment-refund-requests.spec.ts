import { expect, test } from "@playwright/test";

const refundRequest = {
  id: 17,
  request_no: "KAIRQA202609200001",
  payment_order_id: 42,
  order_no: "KAI202609200042",
  payment_status: "paid",
  user: { id: 8, username: "退款测试用户" },
  client_request_id: "refund-request-e2e-001",
  amount_cny: 0.01,
  card_hours: 0.001,
  status: "pending_review",
  reason: "重复充值，希望退回本次款项",
  created_platform: "android",
  reviewed_by: null,
  review_note: null,
  reviewed_at: null,
  payment_refund: null,
  created_at: "2026-09-20T08:00:00Z",
  updated_at: "2026-09-20T08:00:00Z",
};

test("administrator can inspect and reject a customer recharge refund request", async ({ page }) => {
  let reviewed = false;
  await page.context().addCookies([{ name: "kai.locale", value: "zh-CN", domain: "127.0.0.1", path: "/" }]);
  await page.route("**/api/v1/auth/me", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ data: { user: { id: 1, display_name: "平台管理员", email: null, email_verified: false, role: "admin" } }, meta: {} }),
    });
  });
  await page.route("**/api/v1/canonical/admin/payment-refund-requests**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/17/review")) {
      const payload = route.request().postDataJSON() as { action: string; note: string };
      expect(payload).toEqual({ action: "reject", note: "充值单与支付状态已核对" });
      reviewed = true;
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ data: { ...refundRequest, status: "rejected", reviewed_by: 1, review_note: payload.note, reviewed_at: "2026-09-20T08:30:00Z" }, meta: {} }),
      });
      return;
    }
    if (url.pathname.endsWith("/17")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ data: refundRequest, meta: {} }) });
      return;
    }
    const matchesFilter = !reviewed && ["", "pending_review"].includes(url.searchParams.get("status") || "");
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ data: { total: matchesFilter ? 1 : 0, page: 1, page_size: 20, items: matchesFilter ? [refundRequest] : [] }, meta: {} }),
    });
  });

  await page.goto("/admin/refunds");
  await page.locator(".payment-operation-tabs button").nth(1).click();
  await expect(page.getByText(refundRequest.request_no).first()).toBeVisible();
  await expect(page.getByText(/重.*充值，希望退回本次款/)).toBeVisible();
  await expect(page.locator(".payment-operation-actions button").last()).toBeDisabled();

  await page.locator(".payment-operation-actions textarea").fill("充值单与支付状态已核对");
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator(".payment-operation-actions button").first().click();

  await expect.poll(() => reviewed).toBe(true);
  await expect(page.getByText(/已.*回，未.*起人民.*退款/)).toBeVisible();
  await expect(page.getByText(/前.*件下.*有退款申/)).toBeVisible();
  const hasHorizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(hasHorizontalOverflow).toBe(false);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".payment-operation-tabs")).toBeVisible();
  const hasMobileHorizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(hasMobileHorizontalOverflow).toBe(false);
});
