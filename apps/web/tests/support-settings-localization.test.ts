import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { localizePersonName, personNameInputValue, personNameSaveValue } from "../lib/person-name.ts";
import { displayBusinessReference } from "../lib/display-reference.ts";

test("English account display romanizes Chinese names without changing raw editable values", () => {
  assert.equal(localizePersonName("陈志强", "en"), "Chen Zhiqiang");
  assert.equal(localizePersonName("陈志强", "zh-Hans"), "陈志强");
  assert.equal(localizePersonName("陈志强", "zh-Hant"), "陳志強");
  assert.equal(localizePersonName("alice_01", "en"), "alice_01");
  assert.equal(localizePersonName("WOD资讯", "zh-Hans"), "ZTW资讯");
  assert.equal(localizePersonName("WOD资讯", "zh-Hant"), "ZTW資訊");
  assert.equal(localizePersonName("WOD资讯", "en"), "ZTW News");
  assert.equal(personNameInputValue("陈志强", "en", false), "Chen Zhiqiang");
  assert.equal(personNameSaveValue("陈志强", "Chen Zhiqiang", false), "陈志强");
  assert.equal(personNameSaveValue("陈志强", "Chen Z.", true), "Chen Z.");

  const settings = fs.readFileSync(new URL("../components/mobile-account-settings.tsx", import.meta.url), "utf8");
  assert.match(settings, /<h2>\{localizePersonName\(profile\.username, locale\)\}<\/h2>/);
  assert.match(settings, /setUsername\(result\.username \|\| ""\)/);
  assert.match(settings, /value=\{personNameInputValue\(username, locale, usernameEdited\)\}/);
  assert.match(settings, /setUsernameEdited\(true\); setUsername\(event\.target\.value\)/);
  assert.match(settings, /personNameSaveValue\(profile\?\.username, username, usernameEdited\)/);
  assert.match(settings, /updateMobileUserProfile\(value\)/);
  assert.doesNotMatch(settings, /setUsername\(localizePersonName|updateMobileUserProfile\(localizePersonName/);
});

test("Web support requests the selected locale and localizes system UI while preserving user content", () => {
  const api = fs.readFileSync(new URL("../lib/mobile-support-api.ts", import.meta.url), "utf8");
  const support = fs.readFileSync(new URL("../components/mobile-support-workspace.tsx", import.meta.url), "utf8");
  const locale = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

  assert.match(api, /\/chat\/session\?lang=\$\{lang\}/);
  assert.match(api, /client_message_id: crypto\.randomUUID\(\), lang/);
  assert.match(api, /JSON\.stringify\(\{ \.\.\.input, lang \}\)/);
  assert.match(support, /getSupportSession\(locale === "en" \? "en" : "zh"\)/);
  assert.match(support, /sendSupportMessage\(value, session\?\.conversation_id, locale === "en" \? "en" : "zh"\)/);
  assert.match(support, /t\("support\.selfServiceOnline"/);
  assert.match(support, /t\("support\.submitTicket"/);
  assert.doesNotMatch(support, /session\?\.notice|人工坐席尚未配置|人工坐席尚未接入|客服.*未启用/);
  assert.match(support, /<p>\{item\.content\}<\/p>/);
  assert.match(support, /<strong>\{item\.subject\}<\/strong>/);
  assert.match(support, /displayBusinessReference\(item\.ticket_no\)/);
  assert.equal(displayBusinessReference("WOD-20260910-4E9F8B"), "ZTW-20260910-4E9F8B");
  assert.equal(displayBusinessReference("WOD-P-12"), "ZTW-P-12");
  assert.equal(displayBusinessReference("WODR202609100001"), "ZTWR202609100001");
  assert.equal(displayBusinessReference("ZTW-20260910-4E9F8B"), "ZTW-20260910-4E9F8B");
  assert.match(locale, /"support\.assistant": "KAI Self-service Support"/);
  assert.match(locale, /"support\.title": "Help & Support"/);
  assert.match(locale, /"support\.status\.pending": "Pending assignment"/);
});

test("help and support metadata have complete English copy without release placeholders", () => {
  const help = fs.readFileSync(new URL("../app/help/page.tsx", import.meta.url), "utf8");
  const support = fs.readFileSync(new URL("../app/support/page.tsx", import.meta.url), "utf8");
  const simple = fs.readFileSync(new URL("../components/simple-page.tsx", import.meta.url), "utf8");
  const brand = fs.readFileSync(new URL("../components/brand.tsx", import.meta.url), "utf8");
  const locale = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

  assert.match(help, /KAI Sign-in Help/);
  assert.match(help, /same KAI account/);
  assert.doesNotMatch(help, /认证服务完成后|will be published here|北斗 kai account/);
  assert.match(support, /KAI Help & Support/);
  assert.match(simple, />ZTW \/ INFORMATION</);
  assert.match(simple, /locale === "zh-Hant" \? toTraditionalChinese\(simplified\) : simplified/);
  assert.match(brand, /locale === "en" \? <b>KAI<\/b> : <>北斗 <b>kai<\/b><\/>/);
  assert.doesNotMatch(locale, /"support\.assistant": "北斗|"footer\.about": "About 北斗|"auth\.already": "Already have a 北斗/);
});
