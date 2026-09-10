import { expect, test, type Page } from "@playwright/test";

async function mockApis(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    await route.fulfill({ status: 503, json: { error: { message: "Mock unavailable" } } });
  });
}

test("language menu is keyboard accessible and persists the selected locale", async ({ context, page }) => {
  await context.clearCookies();
  await page.addInitScript(() => {
    localStorage.removeItem("kai.locale");
    localStorage.removeItem("kai.color-mode.v1");
  });
  await mockApis(page);
  await page.goto("/login");

  await expect(page.locator("html")).toHaveAttribute("lang", "zh-Hant");
  const trigger = page.locator("button.ui-settings--language:visible");
  await expect(trigger).toHaveAccessibleName("選擇語言，當前語言：繁體中文");
  await expect(trigger).toHaveAttribute("aria-haspopup", "menu");
  await trigger.focus();
  await page.keyboard.press("Enter");

  const menu = page.getByRole("menu");
  await expect(menu).toBeVisible();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await expect(menu.getByText("語言", { exact: true })).toBeVisible();
  await expect(menu.getByText("界面語言", { exact: true })).toBeVisible();
  await expect(menu.getByRole("group", { name: "選擇語言" })).toBeVisible();
  await expect(menu.getByRole("menuitemradio", { name: /繁體中文 zh-TW/i })).toHaveAttribute("aria-checked", "true");
  await expect(menu.getByRole("menuitemradio", { name: /简体中文 zh-CN/i })).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
  await expect(trigger).toBeFocused();

  await trigger.click();
  await menu.getByRole("menuitemradio", { name: /简体中文 zh-CN/i }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-Hans");
  await expect(page.getByRole("button", { name: "选择语言，当前语言：简体中文" })).toBeVisible();
  await expect.poll(async () => (await context.cookies()).find((cookie) => cookie.name === "kai.locale")?.value).toBe("zh-Hans");

  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-Hans");
  await expect(page.getByRole("button", { name: "选择语言，当前语言：简体中文" })).toBeVisible();
});

test("language menu stays inside a narrow dark viewport and closes on outside click", async ({ context, page }) => {
  await context.clearCookies();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => localStorage.setItem("kai.color-mode.v1", "dark"));
  await mockApis(page);
  await page.goto("/login");

  await expect(page.locator("html")).toHaveAttribute("data-color-mode", "dark");
  const trigger = page.locator("button.ui-settings--language:visible");
  await expect(trigger).toHaveAccessibleName("選擇語言，當前語言：繁體中文");
  await trigger.click();
  const menu = page.getByRole("menu");
  await expect(menu).toBeVisible();
  await expect(menu).toHaveCSS("animation-name", "none");

  const bounds = await menu.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.x).toBeGreaterThanOrEqual(14);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(376);
  expect(bounds!.y).toBeGreaterThanOrEqual(0);
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(844);

  await page.mouse.click(12, 240);
  await expect(menu).toBeHidden();
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
});
