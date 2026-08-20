import { defineConfig, devices } from "@playwright/test";
import { resolve } from "node:path";

const frontendDir = __dirname;
const backendDir = resolve(frontendDir, "../backend");
const python = process.env.KAI_BACKEND_PYTHON ?? resolve(
  backendDir,
  process.platform === "win32" ? ".venv313/Scripts/python.exe" : ".venv313/bin/python",
);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 10_000 },
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL: "http://127.0.0.1:9100",
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      name: "backend",
      command: `${JSON.stringify(python)} -m uvicorn app.main:app --host 127.0.0.1 --port 8100`,
      cwd: backendDir,
      url: "http://127.0.0.1:8100/health",
      env: { ...process.env, NEWS_SYNC_ENABLED: "false" },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      name: "frontend",
      command: "npm run dev",
      cwd: frontendDir,
      url: "http://127.0.0.1:9100",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
