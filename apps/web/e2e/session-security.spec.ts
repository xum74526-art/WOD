import { expect, test, type Page } from "@playwright/test";


const EMAIL = "dev-buyer-e2e@example.com";
const PASSWORD = "KaiDev#2026-E2E!";

async function login(page: Page) {
  await page.goto("/login?return_to=/account/settings");
  await page.getByLabel("邮箱").fill(EMAIL);
  await page.getByLabel("密码").fill(PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.waitForURL("**/account/settings");
}

test("账户安全页识别当前设备并退出其他设备", async ({ browser }) => {
  const firstContext = await browser.newContext();
  const secondContext = await browser.newContext();
  const first = await firstContext.newPage();
  const second = await secondContext.newPage();
  try {
    await login(first);
    await login(second);
    await expect(second.getByRole("heading", { name: "账户与安全" })).toBeVisible();
    await expect(second.getByText("当前设备", { exact: true })).toBeVisible();
    second.once("dialog", (dialog) => dialog.accept());
    await second.getByRole("button", { name: "退出其他设备" }).click();
    await expect(second.getByText("其他设备已全部退出")).toBeVisible();
    await expect(second.getByText("1 个有效会话")).toBeVisible();
    const firstStatus = await first.evaluate(async () => (await fetch("http://127.0.0.1:8100/api/v1/auth/me", { credentials: "include" })).status);
    expect(firstStatus).toBe(401);
  } finally {
    await firstContext.close();
    await secondContext.close();
  }
});
