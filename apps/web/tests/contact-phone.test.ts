import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("contact phone is labeled and stays out of unrelated pages", () => {
  const read = (file: string) => readFileSync(new URL(`../components/${file}`, import.meta.url), "utf8");
  const phone = read("contact-phone.tsx");
  assert.match(phone, /<a className=\{styles.phone\} href="tel:\+864001082026">联系我们：\+86 4001082026<\/a>/);
  assert.doesNotMatch(phone, /onClick|onMouse|useEffect|window\.|fetch\(/);
  assert.match(read("auth-panel.tsx"), /<ContactPhone\s*\/>/);
  assert.match(read("mobile-account-settings.tsx"), /<ContactPhone\s*\/>/);
  const authShell = read("auth-shell.tsx");
  assert.match(authShell, /mode === "login" \|\| mode === "register" \? <AuthPanel mode=\{mode\}/);
  for (const source of [
    read("home-page-content.tsx"),
    read("mobile-support-workspace.tsx"),
    read("account-deletion.tsx"),
    readFileSync(new URL("../app/privacy/page.tsx", import.meta.url), "utf8"),
  ]) assert.doesNotMatch(source, /ContactPhone|tel:\+864001082026|\+86 4001082026/);
});
