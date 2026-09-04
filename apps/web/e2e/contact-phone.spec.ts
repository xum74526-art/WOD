import { expect, test, type Page } from "@playwright/test";

async function mockApis(page: Page, mode: "guest" | "error" | "connected" | "loading") {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/auth/me") {
      await route.fulfill({ status: 401, json: { error: { message: "Mock guest" } } });
    } else if (path === "/api/v1/canonical/chat/session") {
      if (mode === "loading") return; // Keep pending until the test closes the page.
      if (mode === "connected") {
        await route.fulfill({ json: { data: { conversation_id: 1, service_mode: "self_service", human_support_configured: false, messages: [], tickets: [], notice: "" } } });
      } else {
        await route.fulfill({ status: mode === "guest" ? 401 : 503, json: { error: { message: "Mock unavailable" } } });
      }
    } else {
      await route.fulfill({ status: 503, json: { error: { message: "Mock unavailable" } } });
    }
  });
}

for (const width of [1280, 390]) {
  test(`home contact is visible without market data at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockApis(page, "guest");
    await page.goto("/");
    const phone = page.getByRole("link", { name: "+86 4001082026", exact: true });
    await expect(phone).toBeVisible();
    await expect(phone).toHaveAttribute("href", "tel:+864001082026");
    const bounds = await phone.boundingBox();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
    await page.screenshot({ path: test.info().outputPath(`home-phone-${width}.png`), fullPage: true, caret: "initial" });
  });
}

for (const mode of ["guest", "error", "connected", "loading"] as const) {
  test(`support contact remains available when ${mode}`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApis(page, mode);
    await page.goto("/support");
    if (mode === "guest") await expect(page.getByRole("heading", { name: "登录后使用在线客服" })).toBeVisible();
    if (mode === "error") await expect(page.getByText("客服请求未完成，请稍后重试。", { exact: true })).toBeVisible();
    if (mode === "connected") await expect(page.getByText("自助客服在线，可查询常见问题并创建客服工单。", { exact: true })).toBeVisible();
    if (mode === "loading") await expect(page.getByText("正在连接在线客服…", { exact: true })).toBeVisible();
    const phone = page.getByRole("link", { name: "+86 4001082026", exact: true });
    await expect(phone).toBeVisible();
    await expect(phone).toHaveAttribute("href", "tel:+864001082026");
    await expect(phone).toHaveText("+86 4001082026");
    await page.screenshot({ path: test.info().outputPath(`support-phone-${mode}.png`), fullPage: true, caret: "initial" });
  });
}
