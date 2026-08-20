import { expect, test, type Page } from "@playwright/test";

const BUYER_EMAIL = "dev-buyer-e2e@example.com";
const SUPPLIER_EMAIL = "dev-supplier-e2e@example.com";
const ADMIN_EMAIL = "dev-seed-admin@example.com";
const PASSWORD = "KaiDev#2026-E2E!";
const REQUEST_TITLE = "E2E：8 张 H100 训练算力需求";

async function login(page: Page, email: string, returnTo: string) {
  await page.goto(`/login?return_to=${encodeURIComponent(returnTo)}`);
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码").fill(PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.waitForURL(`**${returnTo}`);
}

test("买家发布、商家报价、确认交付并完成订单", async ({ browser }) => {
  const buyerContext = await browser.newContext();
  const supplierContext = await browser.newContext();
  const adminContext = await browser.newContext();
  const buyerPage = await buyerContext.newPage();
  const supplierPage = await supplierContext.newPage();
  const adminPage = await adminContext.newPage();
  const browserErrors: string[] = [];
  for (const page of [buyerPage, supplierPage, adminPage]) {
    page.on("console", (message) => {
      if (message.type() === "error") browserErrors.push(message.text());
    });
    page.on("pageerror", (error) => browserErrors.push(error.message));
  }

  try {
    await login(supplierPage, SUPPLIER_EMAIL, "/supplier/resources");
    await supplierPage.getByRole("button", { name: /E2E H100 审核资源池/ }).click();
    await expect(supplierPage.getByText("待审核", { exact: true }).first()).toBeVisible();

    await login(adminPage, ADMIN_EMAIL, "/admin/resources");
    await adminPage.getByRole("button", { name: /E2E H100 审核资源池/ }).click();
    await adminPage.getByRole("button", { name: "审核并发布" }).click();
    await expect(adminPage.getByRole("button", { name: /E2E H100 审核资源池/ })).toHaveCount(0);

    await supplierPage.reload();
    await supplierPage.getByRole("button", { name: /E2E H100 审核资源池/ }).click();
    await expect(supplierPage.getByText("已发布", { exact: true }).first()).toBeVisible();

    await login(buyerPage, BUYER_EMAIL, "/account/requests");
    await buyerPage.getByRole("link", { name: new RegExp(REQUEST_TITLE) }).click();
    await expect(buyerPage.getByRole("heading", { name: REQUEST_TITLE })).toBeVisible();
    await buyerPage.getByRole("button", { name: "确认并公开求购" }).click();
    await expect(buyerPage.getByText("开放报价", { exact: true })).toBeVisible();

    await login(supplierPage, SUPPLIER_EMAIL, "/supplier/requests");
    await supplierPage.getByRole("link", { name: new RegExp(REQUEST_TITLE) }).click();
    await expect(supplierPage.getByRole("heading", { name: REQUEST_TITLE })).toBeVisible();
    await supplierPage.getByLabel("单位报价（USD）").fill("25");
    await supplierPage.getByLabel("交付时间（小时）").fill("2");
    await supplierPage.getByLabel("服务说明").fill("E2E 报价：H100 独占实例，支持 CUDA 12.4。");
    await supplierPage.getByRole("button", { name: "保存报价草稿" }).click();
    await expect(supplierPage.getByRole("heading", { name: "编辑报价草稿" })).toBeVisible();
    await supplierPage.getByLabel("单位报价（USD）").fill("24");
    await supplierPage.getByRole("button", { name: "保存修改" }).click();
    await expect(supplierPage.getByLabel("单位报价（USD）")).toHaveValue("24.000000");
    await supplierPage.getByRole("button", { name: "提交给买家" }).click();
    await expect(supplierPage.getByText("已提交", { exact: true })).toBeVisible();

    await buyerPage.reload();
    await expect(buyerPage.getByText("KAI 开发算力供应商", { exact: true })).toBeVisible();
    await buyerPage.getByRole("button", { name: "列为候选" }).click();
    await expect(buyerPage.getByText("候选", { exact: true })).toBeVisible();

    const acceptResponse = buyerPage.waitForResponse((response) =>
      response.request().method() === "POST" && response.url().endsWith("/accept"),
    );
    await buyerPage.getByRole("button", { name: "接受并生成订单" }).click();
    const response = await acceptResponse;
    expect(response.ok()).toBeTruthy();
    const payload = await response.json() as {
      data: { order_no: string; status: string };
      meta: { idempotent_replay: boolean };
    };
    expect(payload.data.order_no).toMatch(/^WO/);
    expect(payload.data.status).toBe("pending_confirmation");
    expect(payload.meta.idempotent_replay).toBe(false);
    await expect(buyerPage.getByText("已匹配", { exact: true })).toBeVisible();
    await expect(buyerPage.getByText(new RegExp(`已生成订单 ${payload.data.order_no}`))).toBeVisible();

    await supplierPage.goto("/supplier/orders");
    await expect(supplierPage.getByRole("heading", { name: "租赁订单" })).toBeVisible();
    await supplierPage.getByRole("button", { name: new RegExp(payload.data.order_no) }).click();
    await supplierPage.getByRole("button", { name: "确认接单" }).click();
    await expect(supplierPage.getByText("双方已确认", { exact: true }).first()).toBeVisible();

    supplierPage.once("dialog", (dialog) => dialog.accept("E2E：实例初始化中，不包含登录凭据"));
    await supplierPage.getByRole("button", { name: "开始交付" }).click();
    await expect(supplierPage.getByText("交付中", { exact: true }).first()).toBeVisible();

    supplierPage.once("dialog", (dialog) => dialog.accept("E2E：算力实例已准备，请买家验收"));
    await supplierPage.getByRole("button", { name: "标记已交付" }).click();
    await expect(supplierPage.getByText("待买家验收", { exact: true }).first()).toBeVisible();

    await buyerPage.goto("/account/orders");
    await expect(buyerPage.getByRole("heading", { name: "我的订单" })).toBeVisible();
    await buyerPage.getByRole("button", { name: new RegExp(payload.data.order_no) }).click();
    const completeResponse = buyerPage.waitForResponse((result) =>
      result.request().method() === "POST" && result.url().endsWith("/complete"),
    );
    await buyerPage.getByRole("button", { name: "确认验收完成" }).click();
    expect((await completeResponse).ok()).toBeTruthy();
    await expect(buyerPage.getByText("已完成", { exact: true }).first()).toBeVisible();

    expect(browserErrors).toEqual([]);
  } finally {
    await buyerContext.close();
    await supplierContext.close();
    await adminContext.close();
  }
});
