import { expect, test, type Page } from "@playwright/test";


const EMAIL = "dev-buyer-e2e@example.com";
const PASSWORD = "KaiDev#2026-E2E!";

async function login(page: Page) {
  await page.goto("/login?return_to=/account/wallet");
  await page.getByLabel("邮箱").fill(EMAIL);
  await page.getByLabel("密码").fill(PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.waitForURL("**/account/wallet");
}

test("支付与私有存储展示禁用状态，人工 KYC 可真实提交", async ({ page }) => {
  await login(page);
  await expect(page.getByRole("heading", { name: "钱包与流水" })).toBeVisible();
  await expect(page.getByText("等待服务商配置")).toBeVisible();
  await expect(page.getByRole("button", { name: "支付服务未配置" })).toBeDisabled();
  await expect(page.getByText("双分录", { exact: true })).toBeVisible();

  await page.goto("/account/verification");
  await expect(page.getByRole("heading", { name: "实名认证" })).toBeVisible();
  await expect(page.getByText("manual_review 已连接")).toBeVisible();
  await expect(page.getByRole("button", { name: "提交人工审核" })).toBeDisabled();
  await expect(page.getByText("成为商家前需要完成主体实名认证。")).toBeVisible();

  await page.goto("/account/files");
  await expect(page.getByRole("heading", { name: "私有文件" })).toBeVisible();
  await expect(page.getByRole("button", { name: "上传文件" })).toBeDisabled();
  await expect(page.getByText("对象存储接入后开放上传。")).toBeVisible();
});
