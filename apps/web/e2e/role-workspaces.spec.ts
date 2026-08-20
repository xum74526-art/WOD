import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "KaiDev#2026-E2E!";

async function login(page: Page, email: string, returnTo: string) {
  await page.goto(`/login?return_to=${encodeURIComponent(returnTo)}`);
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码").fill(PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.waitForURL(`**${returnTo}`);
}

test("直接登录先返回公开首页，再由控制台入口进入后台", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("邮箱").fill("dev-buyer-e2e@example.com");
  await page.getByLabel("密码").fill(PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL("http://127.0.0.1:9100/");
  await expect(page.getByRole("link", { name: "控制台", exact: true })).toHaveAttribute("href", "/account");
});

test("买家、商家和管理员只看到各自工作台", async ({ browser }) => {
  const buyerContext = await browser.newContext();
  const supplierContext = await browser.newContext();
  const adminContext = await browser.newContext();
  const buyer = await buyerContext.newPage();
  const supplier = await supplierContext.newPage();
  const admin = await adminContext.newPage();

  try {
    await login(buyer, "dev-buyer-e2e@example.com", "/account");
    await expect(buyer.getByRole("navigation", { name: "买家中心导航" })).toBeVisible();
    await expect(buyer.getByRole("link", { name: "申请成为商家", exact: true })).toBeVisible();
    await expect(buyer.getByRole("link", { name: "商家准入" })).toHaveCount(0);
    await buyer.goto("/supplier");
    await expect(buyer).toHaveURL(/\/supplier\/apply$/);

    await login(supplier, "dev-supplier-e2e@example.com", "/supplier");
    await expect(supplier.getByRole("navigation", { name: "商家后台导航" })).toBeVisible();
    await expect(supplier.getByRole("link", { name: "服务器商品", exact: true })).toBeVisible();
    await expect(supplier.getByRole("link", { name: "采购订单" })).toHaveCount(0);
    await expect(supplier.getByRole("link", { name: "账户与安全" })).toBeVisible();
    await supplier.goto("/");
    await expect(supplier.getByRole("link", { name: "控制台", exact: true })).toHaveAttribute("href", "/supplier");
    await expect(supplier.getByRole("link", { name: /管理服务器/ }).first()).toHaveAttribute("href", "/supplier/resources");
    await expect(supplier.getByRole("link", { name: /查看并租用/ })).toHaveCount(0);

    await login(admin, "dev-seed-admin@example.com", "/admin");
    await expect(admin.getByRole("navigation", { name: "管理控制台导航" })).toBeVisible();
    await expect(admin.getByRole("link", { name: "商家准入", exact: true })).toBeVisible();
    await expect(admin.getByRole("link", { name: "采购订单" })).toHaveCount(0);
    await expect(admin.getByRole("link", { name: "申请成为商家" })).toHaveCount(0);
    await admin.goto("/");
    await expect(admin.getByRole("link", { name: "控制台", exact: true })).toHaveAttribute("href", "/admin");
    await expect(admin.getByRole("link", { name: /审核服务器/ }).first()).toHaveAttribute("href", "/admin/resources");
    await expect(admin.getByRole("link", { name: /查看并租用/ })).toHaveCount(0);
    await admin.goto("/account/supplier-review");
    await expect(admin).toHaveURL(/\/admin\/suppliers$/);
    await expect(admin.getByRole("heading", { name: "商家准入审核" })).toBeVisible();
  } finally {
    await buyerContext.close();
    await supplierContext.close();
    await adminContext.close();
  }
});
