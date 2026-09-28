import { expect, test, type Page } from "@playwright/test";

const contactName = "联系我们：+86 4001082026";

test.beforeEach(async ({ context }) => {
  await context.addCookies([{ name: "kai.locale", value: "zh-Hans", domain: "127.0.0.1", path: "/" }]);
});

async function mockApis(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/auth/me") {
      await route.fulfill({ status: 401, json: { error: { message: "Mock guest" } } });
    } else if (path === "/api/v1/canonical/chat/session") {
      await route.fulfill({ status: 401, json: { error: { message: "Mock guest" } } });
    } else {
      await route.fulfill({ status: 503, json: { error: { message: "Mock unavailable" } } });
    }
  });
}

for (const width of [1280, 390]) {
  test(`login and registration show the labeled contact at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockApis(page);
    for (const route of ["/login", "/register"]) {
      await page.goto(route);
      const phone = page.getByRole("link", { name: contactName, exact: true });
      await expect(phone).toBeVisible();
      await expect(phone).toHaveAttribute("href", "tel:+864001082026");
      const bounds = await phone.boundingBox();
      expect(bounds!.x).toBeGreaterThanOrEqual(0);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
    }
    await page.screenshot({ path: test.info().outputPath(`auth-phone-${width}.png`), fullPage: true, caret: "initial" });
  });
}

test("home and support do not show the contact phone", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApis(page);
    await page.goto("/");
    await expect(page.getByRole("link", { name: contactName, exact: true })).toHaveCount(0);
    await page.goto("/support");
    await expect(page.getByRole("heading", { name: "登录后使用在线客服" })).toBeVisible();
    await expect(page.getByRole("link", { name: contactName, exact: true })).toHaveCount(0);
});
