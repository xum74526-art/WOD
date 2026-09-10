import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  DEFAULT_LOCALE,
  localeForFormatting,
  nextLocale,
  normalizeStoredLocale,
  supportApiLanguage,
} from "../lib/language.ts";
import { localizeMarketProductName, localizeMarketRegion, localizeSupplierName } from "../lib/market-localization.ts";
import { toTraditionalChinese } from "../lib/traditional-chinese.ts";

test("Web defaults legacy and unknown language state to Traditional Chinese", () => {
  assert.equal(DEFAULT_LOCALE, "zh-Hant");
  assert.equal(normalizeStoredLocale(undefined), "zh-Hant");
  assert.equal(normalizeStoredLocale("zh"), "zh-Hant");
  assert.equal(normalizeStoredLocale("zh-CN"), "zh-Hant");
  assert.equal(normalizeStoredLocale("zh-TW"), "zh-Hant");
  assert.equal(normalizeStoredLocale("zh-Hans"), "zh-Hans");
  assert.equal(normalizeStoredLocale("en"), "en");
});

test("Web language order, document locale, and support API locale cover all three choices", () => {
  assert.equal(nextLocale("zh-Hant"), "zh-Hans");
  assert.equal(nextLocale("zh-Hans"), "en");
  assert.equal(nextLocale("en"), "zh-Hant");
  assert.equal(localeForFormatting("zh-Hant"), "zh-TW");
  assert.equal(localeForFormatting("zh-Hans"), "zh-CN");
  assert.equal(localeForFormatting("en"), "en-US");
  assert.equal(supportApiLanguage("zh-Hant"), "zh");
  assert.equal(supportApiLanguage("en"), "en");
});

test("Traditional conversion covers fixed copy and backend market content", () => {
  assert.equal(
    toTraditionalChinese("设置、视频上传、账号注销、资产、卡时、联系我们"),
    "設置、視頻上傳、賬號註銷、資產、卡時、聯繫我們",
  );
  assert.equal(localizeSupplierName("北京智算中心", "zh-Hant"), "北京智算中心");
  assert.equal(localizeMarketRegion("华东", "zh-Hant"), "華東");
  assert.equal(localizeMarketProductName("独占训练节点", "zh-Hant"), "獨佔訓練節點");
});

test("Web root, global fallback bridge, and language control expose Traditional Chinese first", () => {
  const layout = fs.readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
  const localeRoot = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");
  const settings = fs.readFileSync(new URL("../components/ui-settings.tsx", import.meta.url), "utf8");

  assert.match(layout, /normalizeStoredLocale\(storedLocale\)/);
  assert.match(layout, /default: "北斗 kai 算力市場"/);
  assert.match(localeRoot, /locale === "zh-Hant" \? toTraditionalChinese\(fallback\)/);
  assert.match(localeRoot, /locale === "zh-Hant"\) return toTraditionalChinese\(raw\)/);
  assert.match(localeRoot, /MutationObserver/);
  assert.match(localeRoot, /"aria-description", "alt"/);
  assert.match(settings, /locale === "zh-Hant" \? "繁" : locale === "zh-Hans" \? "简" : "EN"/);
});
