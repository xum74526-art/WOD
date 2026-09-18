import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

function read(path: string) {
  return fs.readFileSync(new URL(path, import.meta.url), "utf8");
}

test("Web authentication shell uses the shared three-language dictionary", () => {
  const shell = read("../components/auth-shell.tsx");

  for (const key of [
    "auth.login.kicker",
    "auth.register.kicker",
    "auth.security.kicker",
    "auth.intro.loginDescription",
    "auth.intro.registerDescription",
    "auth.intro.securityDescription",
    "auth.rolesLabel",
    "auth.formLabel",
    "auth.footerSecurity",
  ]) assert.match(shell, new RegExp(`t\\(\\"${key}\\"`));

  assert.doesNotMatch(shell, /北斗 kai ACCOUNT ACCESS|JOIN 北斗 kai|locale === "en"/);
});

test("Web authentication actions localize validation, KAI and success states", () => {
  const panel = read("../components/auth-panel.tsx");
  const locale = read("../components/locale-root.tsx");

  for (const key of [
    "auth.captcha.loadFailed",
    "auth.captcha.refreshed",
    "auth.termsRequired",
    "auth.kaiError.termsRequired",
    "auth.kai.sessionCreating",
    "auth.error.credentialsInvalid",
    "auth.error.inviteInvalid",
    "auth.successMessage",
    "auth.captcha.imageAlt",
    "auth.security.session",
  ]) {
    assert.match(panel, new RegExp(key.replaceAll(".", "\\.")));
    assert.match(locale, new RegExp(`"${key}": "[^"]+"`));
  }

  assert.match(panel, /localizedAuthError\(error, t\)/);
  assert.match(panel, /首次完成 KAI 统一认证会自动创建算力星图账号/);
  assert.match(panel, /\(isRegister \|\| method === "kai"\) && !acceptedTerms/);
  assert.match(panel, /\{\(isRegister \|\| method === "kai"\) && \(/);
  assert.doesNotMatch(panel, /identity_not_bound/);
  assert.doesNotMatch(panel, /PENDING_KAI_INTENT_KEY|KAI_REGISTRATION_NOTICE_KEY/);
  assert.doesNotMatch(panel, /locale === "en"|alt="图形验证码"|北斗 kai receives/);
});

test("shared contact phone label follows the selected language", () => {
  const phone = read("../components/contact-phone.tsx");
  const locale = read("../components/locale-root.tsx");

  assert.match(phone, /useI18n\(\)/);
  assert.match(phone, /t\("contact\.phoneLabel", "联系我们：\{phone\}"/);
  assert.match(locale, /"contact\.phoneLabel": "Contact us: \{phone\}"/);
  assert.doesNotMatch(phone, />联系我们：\+86 4001082026</);
});

test("Web forwards the selected language to the canonical API", () => {
  const client = read("../lib/server/canonical-api-client.ts");

  assert.match(client, /request\.cookies\.get\(WEB_LOCALE_COOKIE\)/);
  assert.match(client, /locale === "en" \? "en-US,en;q=0\.9"/);
  assert.match(client, /locale === "zh-Hans" \? "zh-CN,zh;q=0\.9"/);
  assert.match(client, /"zh-TW,zh-Hant;q=0\.9,zh;q=0\.8"/);
  assert.match(client, /headers\.set\(\s*"Accept-Language"/);
});
