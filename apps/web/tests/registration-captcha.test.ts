import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const panel = readFileSync(new URL("../components/auth-panel.tsx", import.meta.url), "utf8");
const locale = readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

test("Web captcha freshness matches the mobile five-minute safety margin", () => {
  assert.match(panel, /const CAPTCHA_FRESHNESS_MS = 270_000/);
  assert.match(panel, /function hasFreshCaptcha\(now = Date\.now\(\)\)[\s\S]*?remaining > 0 && remaining <= CAPTCHA_FRESHNESS_MS/);
  assert.match(panel, /setCaptchaExpiresAt\(Date\.now\(\) \+ CAPTCHA_FRESHNESS_MS\)/);
  assert.match(panel, /document\.visibilityState !== "visible"/);
  assert.match(panel, /document\.addEventListener\("visibilitychange", handleVisibilityChange\)/);
  assert.match(panel, /document\.removeEventListener\("visibilitychange", handleVisibilityChange\)/);
  assert.match(panel, /expiryTimer = setTimeout\(synchronizeCaptcha, remaining\)/);
});

test("refresh clears stale challenge data and deduplicates concurrent requests", () => {
  const refresh = panel.match(/const refreshCaptcha = useCallback\([\s\S]*?\n  \}, \[\]\);/)?.[0] || "";
  const clearCaptcha = refresh.indexOf("setCaptcha(null)");
  const clearCode = refresh.indexOf('setCaptchaCode("")');
  const clearExpiry = refresh.indexOf("setCaptchaExpiresAt(0)");
  const request = refresh.indexOf("getAuthCaptcha()");

  assert.match(refresh, /if \(captchaRefreshPromise\.current\) return captchaRefreshPromise\.current/);
  assert.ok(clearCaptcha >= 0);
  assert.ok(clearCode > clearCaptcha);
  assert.ok(clearExpiry > clearCode);
  assert.ok(request > clearExpiry);
  assert.match(refresh, /if \(!captchaMounted\.current \|\| !captchaContextActive\.current\) return false/);
  assert.match(refresh, /\.finally\(\(\) => \{[\s\S]*?captchaRefreshPromise\.current = null/);
  assert.match(panel, /return \(\) => \{ captchaMounted\.current = false; \}/);
});

test("expired registration captcha is replaced before any register request", () => {
  const submit = panel.match(/async function submit\([\s\S]*?\n  \}/)?.[0] || "";
  const freshnessGuard = submit.indexOf('method === "password" && !hasFreshCaptcha()');
  const registrationRequest = submit.indexOf("await passwordRegister(");

  assert.ok(freshnessGuard >= 0);
  assert.ok(registrationRequest > freshnessGuard);
  assert.match(submit, /await refreshCaptcha\(true\);\s*return/);
  assert.match(panel, /method !== "password"/);
});

test("automatic replacement guidance is available in all Web languages", () => {
  assert.match(panel, /t(?:ranslate\.current)?\("auth\.captcha\.refreshed", "验证码已更新，请重新输入。"\)/);
  assert.match(locale, /"auth\.captcha\.refreshed": "The captcha was refreshed\. Please enter the new code\."/);
});
