import { expect, test, type Page } from "@playwright/test";

const prefix = "/api/v1/canonical/user/account-deletion";
const receiptKey = "wod.account-deletion.receipt.v1";
const ticket = "mock-deletion-scoped-receipt-only-not-a-real-ticket";
const expires = () => new Date(Date.now() + 600_000).toISOString();

async function mockAccount(page: Page, guest = false, handler?: (path: string, body: Record<string, unknown>) => Promise<{ data?: unknown; status?: number; abort?: boolean } | undefined>) {
  // Every API request is intercepted. This suite never submits to a real API,
  // reads a real account, or depends on a business database.
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    let body: Record<string, unknown> = {};
    try { body = route.request().postDataJSON() as Record<string, unknown> || {}; } catch { /* GET */ }
    let response = await handler?.(url.pathname, body);
    if (!response && url.pathname === "/api/v1/auth/me") response = guest
      ? { status: 401 }
      : { data: { user: { id: 1, display_name: "Mock WOD account", email: null, email_verified: false, role: "personal" } } };
    if (!response && url.pathname === `${prefix}/eligibility`) response = guest ? { status: 401 } : { data: { eligible: true, blockers: [], automatic_actions: ["关闭未成交需求并撤回未成交报价"] } };
    if (!response && url.pathname === `${prefix}/verify`) response = { data: { ticket, expires_at: expires() } };
    if (response?.abort) { await route.abort("connectionfailed"); return; }
    const status = response?.status || 200;
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(status >= 400 ? { error: { message: "Mock verification unavailable" } } : { data: response?.data || {}, meta: {} }) });
  });
}

async function reachFinalConfirmation(page: Page) {
  await page.goto("/account-deletion");
  const button = page.getByRole("button", { name: "验证身份并继续" });
  await expect(button).toBeDisabled();
  await expect(page.getByRole("checkbox")).not.toBeChecked();
  await page.getByLabel("WOD 登录密码", { exact: true }).fill("mock-password-not-a-real-account");
  await page.getByRole("checkbox").check();
  await button.click();
  await expect(page.getByRole("heading", { name: "最后确认" })).toBeVisible();
  expect(await page.evaluate((key) => localStorage.getItem(key), receiptKey)).toBeNull();
}

test("public deletion entry works without an installed app or authenticated session", async ({ page }) => {
  await mockAccount(page, true);
  await page.goto("/account-deletion");
  await expect(page.getByRole("heading", { name: "注销 WOD 账号" })).toBeVisible();
  await expect(page.getByRole("link", { name: "登录后继续注销" })).toHaveAttribute("href", "/login?return_to=%2Faccount-deletion");
  await expect(page.getByText("即使已经卸载 App，也可以在此申请注销账号，无需重新安装。")).toBeVisible();
  await expect(page.getByRole("link", { name: "联系我们：+86 4001082026", exact: true })).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath("account-deletion-public.png"), fullPage: true });
});

test("mobile browser keeps the notice and explicit confirmation within the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockAccount(page);
  await reachFinalConfirmation(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: test.info().outputPath("account-deletion-mobile-confirmation.png"), fullPage: true });
});

test("timeout preserves receipt, only checks status after reload, and shows success only when completed", async ({ page }) => {
  let submits = 0;
  let statusCalls = 0;
  const urls: string[] = [];
  page.on("request", (request) => urls.push(request.url()));
  await mockAccount(page, false, async (path, body) => {
    if (path === `${prefix}/submit`) {
      submits += 1;
      expect(body).toEqual({ ticket, confirm: true });
      const stored = await page.evaluate((key) => localStorage.getItem(key), receiptKey);
      expect(JSON.parse(stored!)).toMatchObject({ ticket });
      return { abort: true };
    }
    if (path === `${prefix}/status`) {
      statusCalls += 1;
      expect(body).toEqual({ ticket });
      return { data: { status: statusCalls === 1 ? "processing" : "completed", blockers: [], completed_at: statusCalls === 1 ? null : new Date().toISOString() } };
    }
  });
  await reachFinalConfirmation(page);
  await page.getByRole("button", { name: "确认注销账号", exact: true }).click();
  await expect(page.getByText("注销正在处理中，正常登录已停用。只有服务器确认完成后，才会显示注销成功。")).toBeVisible();
  await expect(page.getByRole("heading", { name: "账号已注销", exact: true })).toHaveCount(0);
  expect(await page.evaluate((key) => localStorage.getItem(key), receiptKey)).not.toContain("password");
  await page.reload();
  await expect(page.getByRole("heading", { name: "账号已注销", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "联系我们：+86 4001082026", exact: true })).toHaveCount(0);
  expect(submits).toBe(1);
  expect(await page.evaluate((key) => localStorage.getItem(key), receiptKey)).toBeNull();
  expect(urls.some((url) => url.includes(ticket) || url.includes("mock-password"))).toBe(false);
  await page.screenshot({ path: test.info().outputPath("account-deletion-completed.png"), fullPage: true });
});

test("server blockers after final confirmation do not look like successful deletion", async ({ page }) => {
  let submits = 0;
  await mockAccount(page, false, async (path) => {
    if (path === `${prefix}/submit`) {
      submits += 1;
      return { data: { status: "blocked", blockers: [{ code: "active_deals", message: "有未结束的撮合合作", count: 2 }], completed_at: null } };
    }
  });
  await reachFinalConfirmation(page);
  await page.getByRole("button", { name: "确认注销账号", exact: true }).click();
  await expect(page.getByText("有未结束的撮合合作 (2)")).toBeVisible();
  await expect(page.getByRole("heading", { name: "账号已注销", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "重新检查条件" }).click();
  await expect(page.getByRole("checkbox")).not.toBeChecked();
  expect(submits).toBe(1);
  expect(await page.evaluate((key) => localStorage.getItem(key), receiptKey)).toBeNull();
});

test("status authorization error neither redirects to ordinary login nor loses the receipt", async ({ page }) => {
  await page.addInitScript(({ key, value }) => localStorage.setItem(key, JSON.stringify(value)), { key: receiptKey, value: { ticket, expiresAt: Date.now() + 86_400_000 } });
  await mockAccount(page, true, async (path) => path === `${prefix}/status` ? { status: 401 } : undefined);
  await page.goto("/account-deletion");
  await expect(page.getByText("目前尚未确认注销结果，请勿重复提交。本浏览器已保留专用查询凭据，可以继续查询。")).toBeVisible();
  await expect(page).toHaveURL(/\/account-deletion$/);
  expect(JSON.parse((await page.evaluate((key) => localStorage.getItem(key), receiptKey))!)).toMatchObject({ ticket });
  await expect(page.getByRole("button", { name: "确认注销账号", exact: true })).toHaveCount(0);
});

test("verified after timeout retains its receipt and requires explicit final confirmation for a same-ticket retry", async ({ page }) => {
  let verifies = 0;
  let submits = 0;
  await mockAccount(page, false, async (path, body) => {
    if (path === `${prefix}/verify`) { verifies += 1; return { data: { ticket, expires_at: expires() } }; }
    if (path === `${prefix}/submit`) {
      submits += 1;
      expect(body.ticket).toBe(ticket);
      return submits === 1 ? { abort: true } : { data: { status: "completed", blockers: [], completed_at: new Date().toISOString() } };
    }
    if (path === `${prefix}/status`) return { data: { status: "verified", blockers: [], completed_at: null } };
  });
  await reachFinalConfirmation(page);
  await page.getByRole("button", { name: "确认注销账号", exact: true }).click();
  await expect(page.getByRole("button", { name: "使用原验证再次确认" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "使用原验证再次确认" })).toBeVisible();
  expect(JSON.parse((await page.evaluate((key) => localStorage.getItem(key), receiptKey))!).ticket).toBe(ticket);
  expect(submits).toBe(1);
  expect(verifies).toBe(1);
  await page.getByRole("button", { name: "使用原验证再次确认" }).click();
  await expect(page.getByRole("heading", { name: "确认再次提交" })).toBeVisible();
  expect(submits).toBe(1);
  await page.getByRole("button", { name: "确认重试注销", exact: true }).click();
  await expect(page.getByRole("heading", { name: "账号已注销", exact: true })).toBeVisible();
  expect(submits).toBe(2);
  expect(verifies).toBe(1);
});

test("processing blockers explain unfinished cleanup and cannot show completion", async ({ page }) => {
  await page.addInitScript(({ key, value }) => localStorage.setItem(key, JSON.stringify(value)), { key: receiptKey, value: { ticket, expiresAt: Date.now() + 86_400_000 } });
  await mockAccount(page, false, async (path) => path === `${prefix}/status`
    ? { data: { status: "processing", blockers: [{ code: "late_payment", message: "有需要核对的支付记录", count: 1 }], completed_at: null } }
    : undefined);
  await page.goto("/account-deletion");
  await expect(page.getByText("正常登录已停用，但以下未处理事项阻止了资料清理，注销尚未完成。")).toBeVisible();
  await expect(page.getByText("有需要核对的支付记录")).toBeVisible();
  await expect(page.getByRole("link", { name: "联系我们：+86 4001082026", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "账号已注销", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "确认重试注销", exact: true })).toHaveCount(0);
});
