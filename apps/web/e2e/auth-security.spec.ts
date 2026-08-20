import { expect, test } from "@playwright/test";


test("密码找回入口不会伪造未配置的邮件发送", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("link", { name: "忘记密码？" }).click();
  await expect(page).toHaveURL(/\/forgot-password$/);
  await expect(page.getByRole("heading", { name: "找回 KAI 密码" })).toBeVisible();
  await page.getByLabel("注册邮箱").fill("dev-buyer-e2e@example.com");
  await page.getByRole("button", { name: "发送密码重置邮件" }).click();
  await expect(page.getByText("密码重置邮件服务尚未配置")).toBeVisible();
});
