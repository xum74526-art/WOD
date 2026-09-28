import { expect, test, type APIRequestContext } from "@playwright/test";

const E2E_CAPTCHA_CODE = process.env.WEB_E2E_CAPTCHA_CODE || "A2BC";

async function register(request: APIRequestContext) {
  const captchaResponse = await request.get("/api/v1/auth/captcha");
  expect(captchaResponse.ok()).toBeTruthy();
  expect(captchaResponse.headers()["cache-control"]).toContain("no-store");
  const captcha = (await captchaResponse.json()).data as { key: string; image: string };
  expect(captcha.image).toMatch(/^data:image\/png;base64,/);
  const phone = `137${String(Date.now()).slice(-8)}`;
  const response = await request.post("/api/v1/auth/password/register", {
    data: {
      display_name: "Web E2E 用户",
      identifier: phone,
      password: "LocalTest123",
      captcha_key: captcha.key,
      captcha_code: E2E_CAPTCHA_CODE,
    },
  });
  expect(response.ok()).toBeTruthy();
  return phone;
}

test("Web BFF never caches or reuses a captcha challenge", async ({ request }) => {
  const firstResponse = await request.get("/api/v1/auth/captcha");
  const secondResponse = await request.get("/api/v1/auth/captcha");

  expect(firstResponse.ok()).toBeTruthy();
  expect(secondResponse.ok()).toBeTruthy();
  expect(firstResponse.headers()["cache-control"]).toContain("no-store");
  expect(secondResponse.headers()["cache-control"]).toContain("no-store");

  const first = (await firstResponse.json()).data as { key: string };
  const second = (await secondResponse.json()).data as { key: string };
  expect(second.key).not.toBe(first.key);
});

test("Web BFF 健康检查与公开商品使用统一后端", async ({ request }) => {
  const health = await request.get("/api/v1/health");
  expect(health.ok()).toBeTruthy();
  await expect(health.json()).resolves.toMatchObject({ data: { mobile_backend: "ok" } });

  const products = await request.get("/api/v1/public/products");
  expect(products.ok()).toBeTruthy();
  await expect(products.json()).resolves.toMatchObject({ meta: { source: "canonical-api" } });

  for (const path of ["/api/v1/canonical/market/models", "/api/v1/canonical/market/sources/status", "/api/v1/canonical/market/ranking"]) {
    const response = await request.get(path);
    expect(response.ok(), `${path} should be available`).toBeTruthy();
    await expect(response.json()).resolves.toMatchObject({ meta: { source: "canonical-api" } });
  }
});

test("Web 注册、Cookie 会话、地址与通知全部使用手机端后端", async ({ request }) => {
  await register(request);

  const me = await request.get("/api/v1/auth/me");
  expect(me.ok()).toBeTruthy();
  await expect(me.json()).resolves.toMatchObject({ data: { user: { display_name: "Web E2E 用户", role: "personal" } } });

  const created = await request.post("/api/v1/account/addresses", {
    data: {
      label: "E2E",
      recipient_name: "测试用户",
      phone: "13800138000",
      province: "上海市",
      city: "上海市",
      district: "浦东新区",
      address_line: "联调路 1 号",
    },
  });
  expect(created.ok()).toBeTruthy();

  const addresses = await request.get("/api/v1/account/addresses");
  const addressPayload = await addresses.json();
  expect(addressPayload.data).toContainEqual(expect.objectContaining({ label: "E2E", address_line: "联调路 1 号" }));

  const notifications = await request.get("/api/v1/notifications");
  expect(notifications.ok()).toBeTruthy();
  await expect(notifications.json()).resolves.toMatchObject({ meta: { unread: expect.any(Number) } });
});

test("新增的个人中心功能全部通过 BFF 使用统一业务接口", async ({ request }) => {
  await register(request);

  const paths = [
    "/api/v1/canonical/assets",
    "/api/v1/canonical/revenue",
    "/api/v1/canonical/revenue/chart?range_days=30",
    "/api/v1/canonical/revenue/records",
    "/api/v1/canonical/user/rebate",
    "/api/v1/canonical/invite/summary",
    "/api/v1/canonical/invite/records",
    "/api/v1/canonical/invite/commissions?page=1&page_size=50",
    "/api/v1/canonical/coupons",
    "/api/v1/canonical/bank-cards",
    "/api/v1/canonical/bank-cards/config",
    "/api/v1/canonical/verification",
    "/api/v1/canonical/withdrawals/config",
    "/api/v1/canonical/withdrawals?page=1&page_size=20",
    "/api/v1/canonical/payments/mapay/config",
    "/api/v1/canonical/onboarding/mine",
    "/api/v1/canonical/buy-requests/summary",
  ];

  for (const path of paths) {
    const response = await request.get(path);
    expect(response.ok(), `${path} should be available`).toBeTruthy();
    await expect(response.json()).resolves.toMatchObject({ meta: { source: "canonical-api" } });
  }

  const wallet = await request.get("/api/v1/account/wallet");
  expect(wallet.ok()).toBeTruthy();
  await expect(wallet.json()).resolves.toMatchObject({
    data: { balances: [{ currency: "CARD_HOURS" }], ledger_mode: "mobile_ledger" },
  });

  const mobileWallet = await request.get("/api/v1/canonical/wallet");
  await expect(mobileWallet.json()).resolves.toMatchObject({
    data: {
      balance: expect.any(Number),
      withdrawable_balance: expect.any(Number),
      withdraw_frozen: expect.any(Number),
      payment_config: expect.any(Object),
    },
  });

  const identity = await request.post("/api/v1/canonical/verification", {
    data: { real_name: "张三", id_card: "11010519491231002X", sensitive_consent: true },
  });
  expect(identity.ok()).toBeTruthy();
  const onePixelPng = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=", "base64");
  const photos = await request.post("/api/v1/canonical/verification/upload", {
    multipart: {
      front: { name: "front.png", mimeType: "image/png", buffer: onePixelPng },
      back: { name: "back.png", mimeType: "image/png", buffer: onePixelPng },
    },
  });
  expect(photos.ok()).toBeTruthy();
  await expect(photos.json()).resolves.toMatchObject({
    data: { front_photo_uploaded: true, back_photo_uploaded: true },
    meta: { source: "canonical-api" },
  });
});

test("账户设置、通知偏好、社区、客服和求购使用统一后端状态机", async ({ request }) => {
  await register(request);

  const profile = await request.put("/api/v1/canonical/user/profile", { data: { username: "Web 同步用户" } });
  expect(profile.ok()).toBeTruthy();
  await expect(profile.json()).resolves.toMatchObject({ data: { username: "Web 同步用户" } });

  const preferences = await request.put("/api/v1/canonical/notifications/preferences", { data: { order_enabled: false } });
  expect(preferences.ok()).toBeTruthy();
  await expect(preferences.json()).resolves.toMatchObject({ data: { preferences: { order_enabled: false } } });

  const post = await request.post("/api/v1/canonical/community/posts", { data: { content: "Web 与 App 社区联调", topic: "E2E" } });
  expect(post.ok()).toBeTruthy();
  const postId = ((await post.json()).data as { id: number }).id;
  const like = await request.post(`/api/v1/canonical/community/posts/${postId}/like`);
  expect(like.ok(), `community like failed (${like.status()}): ${await like.text()}`).toBeTruthy();
  expect((await request.post(`/api/v1/canonical/community/posts/${postId}/comments`, { data: { content: "联调评论" } })).ok()).toBeTruthy();

  const support = await request.post("/api/v1/canonical/chat", {
    data: { message: "如何查看订单？", client_message_id: `web-e2e-${Date.now()}`, lang: "zh" },
  });
  expect(support.ok()).toBeTruthy();
  await expect(support.json()).resolves.toMatchObject({ data: { conversation_id: expect.any(Number), reply: expect.any(String) } });

  const buyRequest = await request.post("/api/v1/canonical/buy-requests", {
    data: { request_type: "online", gpu_model: "RTX4090", quantity: 1, gpu_hours: 24, currency: "CNY", requirements: {}, expires_in_hours: 24 },
  });
  expect(buyRequest.ok()).toBeTruthy();
  await expect(buyRequest.json()).resolves.toMatchObject({ data: { request_type: "online", gpu_model: "RTX4090", status: "published" } });
});

test("Kai Web 入口由 BFF 处理而不是落入旧模块", async ({ request }) => {
  const response = await request.get("/api/v1/auth/kai/start?intent=login&return_to=%2Faccount", { maxRedirects: 0 });
  expect(response.status()).toBe(503);
  await expect(response.json()).resolves.toMatchObject({ error: { code: "mobile_backend_error" } });
});

test("跨站写请求被 BFF 拒绝", async ({ request }) => {
  const response = await request.post("/api/v1/auth/logout", {
    headers: { Origin: "https://evil.example" },
  });
  expect(response.status()).toBe(403);
  await expect(response.json()).resolves.toMatchObject({ error: { code: "origin_mismatch" } });
});

test("网站根据持久化语言 Cookie 输出中英文页面", async ({ request }) => {
  const english = await request.get("/", { headers: { Cookie: "kai.locale=en" } });
  expect(english.ok()).toBeTruthy();
  const englishHtml = await english.text();
  expect(englishHtml).toContain('lang="en"');
  expect(englishHtml).toContain("GPU servers");
  expect(englishHtml).toContain("Compute Market");

  const chinese = await request.get("/", { headers: { Cookie: "kai.locale=zh-Hans" } });
  expect(chinese.ok()).toBeTruthy();
  const chineseHtml = await chinese.text();
  expect(chineseHtml).toContain('lang="zh-Hans"');
  expect(chineseHtml).toContain("GPU 服务器");
  expect(chineseHtml).toContain("算力市场");
});
