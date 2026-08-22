import { defineConfig, devices } from "@playwright/test";
import { resolve } from "node:path";

const frontendDir = __dirname;
const backendDir = resolve(frontendDir, "../../services/api");
const webPort = Number(process.env.WEB_E2E_PORT || 9100);
const apiPort = Number(process.env.API_E2E_PORT || 8000);
const python = process.env.API_PYTHON ?? resolve(
  backendDir,
  process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python",
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
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
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
      command: `${JSON.stringify(python)} -m uvicorn app.main:app --host 127.0.0.1 --port ${apiPort} --workers 1`,
      cwd: backendDir,
      url: `http://127.0.0.1:${apiPort}/health`,
      env: { ...process.env, MARKET_HISTORY_SYNC_ENABLED: "false", COMMUNITY_ONLINE_ENABLED: "false" },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      name: "frontend",
      command: `./node_modules/.bin/next dev -p ${webPort}`,
      cwd: frontendDir,
      url: `http://127.0.0.1:${webPort}`,
      env: { ...process.env, API_ORIGIN: `http://127.0.0.1:${apiPort}` },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
