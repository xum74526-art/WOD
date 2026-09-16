import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  buildLocalizedMetadata,
  type LocalizedMetadataCopy,
} from "../lib/localized-metadata.ts";

const sampleCopy: LocalizedMetadataCopy = {
  "zh-Hant": { title: "繁中標題", description: "繁中說明" },
  "zh-Hans": { title: "简中标题", description: "简中说明" },
  en: { title: "English title", description: "English description" },
};

test("localized metadata selects all three supported locales and keeps shared directives", () => {
  assert.deepEqual(buildLocalizedMetadata("zh-Hant", sampleCopy), {
    title: { absolute: "繁中標題" },
    description: "繁中說明",
  });
  assert.deepEqual(buildLocalizedMetadata("zh-Hans", sampleCopy), {
    title: { absolute: "简中标题" },
    description: "简中说明",
  });
  assert.deepEqual(buildLocalizedMetadata("en", sampleCopy, {
    robots: { index: false, follow: false },
  }), {
    robots: { index: false, follow: false },
    title: { absolute: "English title" },
    description: "English description",
  });
});

test("high-visibility pages derive metadata from the locale cookie helper", () => {
  const pagePaths = [
    "../app/login/page.tsx",
    "../app/register/page.tsx",
    "../app/forgot-password/page.tsx",
    "../app/reset-password/page.tsx",
    "../app/account/settings/page.tsx",
    "../app/contact/page.tsx",
    "../app/privacy/page.tsx",
    "../app/support/page.tsx",
    "../app/terms/page.tsx",
    "../app/trend/page.tsx",
  ];

  for (const pagePath of pagePaths) {
    const source = fs.readFileSync(new URL(pagePath, import.meta.url), "utf8");
    assert.match(source, /localizedPageMetadata\(\{/);
    assert.match(source, /"zh-Hant": \{/);
    assert.match(source, /"zh-Hans": \{/);
    assert.match(source, /en: \{/);
    assert.doesNotMatch(source, /export const metadata/);
  }

  const serverHelper = fs.readFileSync(new URL("../lib/server/localized-metadata.ts", import.meta.url), "utf8");
  assert.match(serverHelper, /cookieStore\.get\("kai\.locale"\)/);
  assert.match(serverHelper, /normalizeStoredLocale/);
});

test("workspace accessibility labels and unknown ticket status use localized copy", () => {
  const locale = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");
  const shell = fs.readFileSync(new URL("../components/product-shell.tsx", import.meta.url), "utf8");
  const support = fs.readFileSync(new URL("../components/mobile-support-workspace.tsx", import.meta.url), "utf8");

  for (const key of [
    "workspace.verifying",
    "accessibility.skipToContent",
    "workspace.navigation",
    "support.status.unknown",
  ]) {
    assert.match(locale, new RegExp(`"${key.replaceAll(".", "\\.")}": "[^"]+"`));
  }
  assert.match(shell, /t\("workspace\.verifying", "正在验证工作台权限"\)/);
  assert.match(shell, /t\("accessibility\.skipToContent", "跳到主要内容"\)/);
  assert.match(shell, /t\("workspace\.navigation", "\{name\}导航", \{ name: workspaceName \}\)/);
  assert.doesNotMatch(shell, /aria-label="正在验证工作台权限"/);
  assert.match(support, /t\("support\.status\.unknown", "状态待确认"\)/);
  assert.doesNotMatch(support, /: item\.status/);
});
