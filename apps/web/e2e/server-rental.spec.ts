import { expect, test, type Page } from "@playwright/test";

const BUYER_EMAIL = "dev-buyer-e2e@example.com";
const SUPPLIER_EMAIL = "dev-supplier-e2e@example.com";
const PASSWORD = "KaiDev#2026-E2E!";
const PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA browser-e2e";

async function login(page: Page, email: string, returnTo: string) {
  await page.goto(`/login?return_to=${encodeURIComponent(returnTo)}`);
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码").fill(PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.waitForURL(`**${returnTo}`);
}

test("买家公钥、服务器购买、SSH 使用和商家租约形成闭环", async ({ browser }) => {
  const buyerContext = await browser.newContext();
  const supplierContext = await browser.newContext();
  const buyer = await buyerContext.newPage();
  const supplier = await supplierContext.newPage();
  try {
    await login(buyer, BUYER_EMAIL, "/account/ssh-keys");
    if (await buyer.getByText("浏览器 E2E", { exact: true }).count() === 0) {
      await buyer.getByRole("button", { name: "添加公钥" }).click();
      await buyer.getByLabel("设备名称").fill("浏览器 E2E");
      await buyer.getByLabel("公钥内容").fill(PUBLIC_KEY);
      await buyer.getByRole("button", { name: "保存公钥" }).click();
      await expect(buyer.getByText("浏览器 E2E", { exact: true })).toBeVisible();
    }

    await buyer.goto("/market");
    await expect(buyer.getByRole("heading", { name: "商家服务器" })).toBeVisible();
    const server = buyer.getByRole("article").filter({ hasText: "开发演示 H100 资源池" });
    await server.getByRole("link", { name: "查看并租用" }).click();
    await expect(buyer.getByText("买家自己的 SSH 公钥", { exact: true })).toBeVisible();
    await buyer.getByRole("button", { name: "付款并获取 SSH 权限" }).click();
    await expect(buyer).toHaveURL(/\/account\/leases\?lease=\d+$/);
    await expect(buyer.getByRole("heading", { name: "我的服务器" })).toBeVisible();
    await expect(buyer.getByText(/ssh .*@127\.0\.0\.1/)).toBeVisible();
    await expect(buyer.getByRole("button", { name: "复制命令" })).toBeVisible();

    await login(supplier, SUPPLIER_EMAIL, "/supplier/leases");
    await expect(supplier.getByRole("heading", { name: "服务器租约" })).toBeVisible();
    await expect(supplier.getByText("开发演示 H100 资源池", { exact: true })).toBeVisible();
    await expect(supplier.getByText("仅显示指纹", { exact: true }).first()).toBeVisible();

    await supplier.goto("/supplier/servers");
    const agentServer = supplier.getByRole("article").filter({ hasText: "开发演示 H100 资源池" });
    await agentServer.getByRole("button", { name: "安装 Agent" }).click();
    await expect(supplier.getByRole("heading", { name: "安装 KAI Agent" })).toBeVisible();
    await expect(supplier.getByText("Linux", { exact: true })).toBeVisible();
    await supplier.getByRole("button", { name: "Windows", exact: true }).click();
    await expect(supplier.getByText(/管理员 PowerShell/)).toBeVisible();
    await supplier.getByRole("button", { name: "Docker", exact: true }).click();
    await expect(supplier.getByText(/Docker 源包/)).toBeVisible();
    await expect(supplier.getByRole("link", { name: /kai-agent-docker-context/ })).toBeVisible();
  } finally {
    await buyerContext.close();
    await supplierContext.close();
  }
});
