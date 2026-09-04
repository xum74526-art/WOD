import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("home and both support states expose the same plain phone number", () => {
  const read = (file: string) => readFileSync(new URL(`../components/${file}`, import.meta.url), "utf8");
  const phone = read("contact-phone.tsx");
  assert.match(phone, /<a className=\{styles.phone\} href="tel:\+864001082026">\+86 4001082026<\/a>/);
  assert.doesNotMatch(phone, /onClick|onMouse|useEffect|window\.|fetch\(/);
  assert.match(read("home-page-content.tsx"), /<ContactPhone\s*\/>/);
  const support = read("mobile-support-workspace.tsx");
  assert.match(support.slice(support.indexOf('if (loginRequired)'), support.indexOf('<section className="support-workspace">')), /<ContactPhone\s*\/>/);
  assert.match(support.slice(support.indexOf('<section className="support-workspace">')), /<ContactPhone\s*\/>/);
});
