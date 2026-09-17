import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { recoveryTokenFromUrl } from "../lib/account-recovery-url.ts";

const emailToken = "email-recovery-token-abcdefghijklmnopqrstuvwxyz";
const kaiToken = "kai-recovery-token-abcdefghijklmnopqrstuvwxyz12";

function read(path: string) {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

test("email and KAI proofs are consumed from fragments and removed from the visible URL", () => {
  assert.deepEqual(
    recoveryTokenFromUrl(`https://wod.kai.com/verify-email?source=mail#token=${emailToken}&view=compact`, ["token"]),
    { token: emailToken, source: "fragment", cleanPath: "/verify-email?source=mail#view=compact" },
  );
  assert.deepEqual(
    recoveryTokenFromUrl(`https://wod.kai.com/reset-password#kai_recovery_token=${kaiToken}`),
    { token: kaiToken, source: "fragment", cleanPath: "/reset-password" },
  );
});

test("query tokens are rejected and removed without being used", () => {
  assert.deepEqual(
    recoveryTokenFromUrl(`https://wod.kai.com/reset-password?campaign=legacy&token=${emailToken}`),
    { token: "", source: null, cleanPath: "/reset-password?campaign=legacy" },
  );
  assert.deepEqual(
    recoveryTokenFromUrl(`https://wod.kai.com/reset-password?campaign=legacy&kai_recovery_token=${kaiToken}#view=compact`),
    { token: "", source: null, cleanPath: "/reset-password?campaign=legacy#view=compact" },
  );
});

test("BFF exposes only the scoped recovery routes and keeps public proofs unauthenticated and no-store", () => {
  const adapter = read("../lib/api-adapter.ts");
  for (const route of [
    "auth/recovery/config",
    "user/recovery-email",
    "user/recovery-email/request-verification",
    "auth/email/verification/confirm",
    "auth/email/password-reset/request",
    "auth/email/password-reset/confirm",
  ]) assert.match(adapter, new RegExp(`path === ["']${route.replaceAll("/", "\\/")}["']`));
  for (const upstream of [
    "/api/auth/recovery/config",
    "/api/auth/email/verification/confirm",
    "/api/auth/email/password-reset/request",
    "/api/auth/email/password-reset/confirm",
  ]) assert.match(adapter, new RegExp(`${upstream.replaceAll("/", "\\/")}["'][\\s\\S]{0,180}auth: false`));
  assert.match(adapter, /function recoveryApiResponse[\s\S]*Cache-Control["'], ["']private, no-store[\s\S]*Referrer-Policy["'], ["']no-referrer/);
});

test("KAI recovery returns only to reset-password and does not create the normal return cookie", () => {
  const adapter = read("../lib/api-adapter.ts");
  assert.match(adapter, /requestedIntent === "register" \|\| requestedIntent === "recover"/);
  assert.match(adapter, /recovering \? "\/reset-password" : "\/login"/);
  assert.match(adapter, /if \(!recovering\) \{[\s\S]*response\.cookies\.set\(RETURN_TO_COOKIE/);
  const api = read("../lib/api.ts");
  assert.match(api, /"login" \| "register" \| "recover"/);
  assert.match(api, /if \(intent !== "recover"\) query\.set\("return_to", returnTo\)/);
});

test("recovery UI distinguishes linked-email settings from email recovery and never persists the proof", () => {
  const recovery = read("../components/password-recovery-panel.tsx");
  const verification = read("../components/email-verification-result.tsx");
  const verifyPage = read("../app/verify-email/page.tsx");
  const authShell = read("../components/auth-shell.tsx");
  const settings = read("../components/mobile-account-settings.tsx");
  assert.match(recovery, /邮箱找回/);
  assert.match(recovery, /已绑定邮箱/);
  assert.match(settings, /绑定邮箱/);
  assert.match(verification, /绑定邮箱验证完成/);
  assert.match(verifyPage, /驗證綁定郵箱/);
  assert.doesNotMatch(recovery + verification + verifyPage + authShell + settings, /找回邮箱/);
  assert.match(recovery, /kaiWebAuthorizationUrl\("recover"\)/);
  assert.match(recovery, /无论邮箱是否存在，页面都会显示相同结果/);
  assert.match(recovery + verification, /window\.history\.replaceState/);
  assert.doesNotMatch(recovery + verification, /localStorage|sessionStorage/);
  assert.doesNotMatch(recovery + verification, /searchParams\.get\(["']token["']\)/);
  assert.doesNotMatch(verifyPage, /searchParams|token=/);
});

test("account recovery and verification UI ship complete English copy under the 算力星图 brand", () => {
  const recovery = read("../components/password-recovery-panel.tsx");
  const verification = read("../components/email-verification-result.tsx");
  const localeRoot = read("../components/locale-root.tsx");
  assert.match(recovery, /useI18n\(\)/);
  assert.match(verification, /useI18n\(\)/);
  const referencedKeys = new Set(
    [...(recovery + verification).matchAll(/"(auth\.recovery\.[^"]+)"/g)].map((match) => match[1]!),
  );
  assert.ok(referencedKeys.size >= 40, "expected all recovery states and actions to be localized");
  for (const key of referencedKeys) assert.match(localeRoot, new RegExp(`"${key.replaceAll(".", "\\.")}"\\s*:`));
  assert.match(localeRoot, /"auth\.intro\.forgot": "Recover your 算力星图 account"/);
  assert.doesNotMatch(localeRoot, /"auth\.intro\.forgot": "Recover your (?:ZTW|KAI) account"/);
  assert.match(localeRoot, /"settings\.recoveryEmail": "Email binding"/);
  assert.match(localeRoot, /"settings\.recoveryEmailVerified": "Linked email"/);
  assert.match(localeRoot, /"auth\.recovery\.emailMethod": "Email recovery"/);
  assert.match(localeRoot, /"auth\.recovery\.boundEmail": "Linked email"/);
});

test("account settings shows verified status and requires the current password before binding or changing email", () => {
  const settings = read("../components/mobile-account-settings.tsx");
  const api = read("../lib/api.ts");
  assert.match(settings, /getRecoveryEmailStatus/);
  assert.match(settings, /requestRecoveryEmailVerification\(recoveryForm\.email\.trim\(\), recoveryForm\.currentPassword\)/);
  assert.match(settings, /type="password" autoComplete="current-password"/);
  assert.match(settings, /recoveryEmail\?\.verified/);
  assert.match(settings, /EMAIL BINDING/);
  assert.doesNotMatch(settings, /找回邮箱/);
  assert.match(api, /\/api\/v1\/user\/recovery-email\/request-verification/);
});
