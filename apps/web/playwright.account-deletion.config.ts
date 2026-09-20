import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.WEB_DELETION_E2E_PORT || 9197);

export default defineConfig({
  testDir: "./e2e",
  testMatch: "account-deletion.spec.ts",
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: "list",
  use: { baseURL: `http://127.0.0.1:${port}`, locale: "zh-CN", screenshot: "only-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  // Mock-only UI checks: no FastAPI process, real credentials, or database.
  webServer: {
    command: `node ./node_modules/next/dist/bin/next dev --hostname 127.0.0.1 -p ${port}`,
    url: `http://127.0.0.1:${port}/account-deletion`,
    env: { API_ORIGIN: "http://127.0.0.1:9", API_ALLOW_INSECURE_HTTP: "true" },
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
