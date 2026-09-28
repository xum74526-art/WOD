import { defineConfig, devices } from "@playwright/test";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = dirname(fileURLToPath(import.meta.url));
const backendDir = resolve(frontendDir, "../../services/api");
const webPort = Number(process.env.WEB_E2E_PORT || 9100);
const apiPort = Number(process.env.API_E2E_PORT || 8000);
const e2eCaptchaCode = process.env.WEB_E2E_CAPTCHA_CODE || "A2BC";
const tempRoot = resolve(tmpdir());
const inheritedStateDir = process.env.ZTW_PLAYWRIGHT_STATE_DIR?.trim();
const safeInheritedStateDir = inheritedStateDir && dirname(resolve(inheritedStateDir)) === tempRoot
  && basename(resolve(inheritedStateDir)).startsWith("ztw-playwright-e2e-");
const e2eStateDir = safeInheritedStateDir
  ? resolve(inheritedStateDir)
  : mkdtempSync(join(tempRoot, "ztw-playwright-e2e-"));
process.env.ZTW_PLAYWRIGHT_STATE_DIR = e2eStateDir;
const e2eDatabasePath = resolve(e2eStateDir, "api.sqlite3").replaceAll("\\", "/");
const e2eUploadRoot = resolve(e2eStateDir, "uploads");
const e2eSessionSecret = createHash("sha256").update("ztw-playwright-e2e-session").digest("hex");
const e2eSensitiveDataKey = `${createHash("sha256").update("ztw-playwright-e2e-sensitive-storage").digest("base64url")}=`;
mkdirSync(e2eStateDir, { recursive: true });
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
      command: `${JSON.stringify(python)} -m uvicorn tests.e2e_app:app --host 127.0.0.1 --port ${apiPort} --workers 1`,
      cwd: backendDir,
      url: `http://127.0.0.1:${apiPort}/health`,
      env: {
        ...process.env,
        COMMUNITY_ONLINE_ENABLED: "false",
        ACCOUNT_RECOVERY_EMAIL_ENABLED: "false",
        AI_PROVIDER: "",
        AI_API_KEY: "",
        DEEPSEEK_API_KEY: "",
        KAI_AUTH_ISSUER: "",
        KAI_AUTH_CLIENT_ID: "",
        KAI_AUTH_CLIENT_SECRET: "",
        KAI_AUTH_CALLBACK_URL: "",
        SECRET_KEY: e2eSessionSecret,
        SENSITIVE_DATA_KEY: e2eSensitiveDataKey,
        DATABASE_URL: `sqlite:///${e2eDatabasePath}`,
        UPLOAD_ROOT: e2eUploadRoot,
        ZTW_PLAYWRIGHT_E2E: "1",
        ZTW_E2E_CAPTCHA_CODE: e2eCaptchaCode,
      },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      name: "frontend",
      command: `${JSON.stringify(process.execPath)} node_modules/next/dist/bin/next dev -p ${webPort}`,
      cwd: frontendDir,
      url: `http://127.0.0.1:${webPort}`,
      env: {
        ...process.env,
        API_ORIGIN: `http://127.0.0.1:${apiPort}`,
        API_ALLOW_INSECURE_HTTP: "true",
      },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
