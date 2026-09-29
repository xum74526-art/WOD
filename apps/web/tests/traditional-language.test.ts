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
  assert.match(layout, /default: "KAI星算算力市場"/);
  assert.match(localeRoot, /locale === "zh-Hant" \? toTraditionalChinese\(fallback\)/);
  assert.match(localeRoot, /locale === "zh-Hant"\) return localizeLegacyCurrencyTerms\(toTraditionalChinese\(raw\), locale, displayCurrencyConfig\)/);
  for (const key of [
    "market.kai.directDescription",
    "market.merchant.directDescription",
    "market.availableDirect",
    "market.unavailableDirect",
  ]) {
    assert.match(localeRoot, new RegExp(`"${key}": "[^"]+"`));
  }
  assert.match(localeRoot, /MutationObserver/);
  assert.match(localeRoot, /"aria-description", "alt"/);
  assert.match(settings, /value: "zh-Hant", label: "繁體中文"/);
  assert.match(settings, /value: "zh-Hans", label: "简体中文"/);
  assert.match(settings, /value: "en", label: "English"/);
  assert.match(settings, /DropdownMenu\.Root/);
  assert.match(settings, /DropdownMenu\.RadioGroup/);
  assert.match(settings, /DropdownMenu\.RadioItem/);
  assert.match(settings, /code: "zh-TW"/);
  assert.match(settings, /code: "zh-CN"/);
  assert.match(settings, /code: "en-US"/);
  assert.match(settings, /data-i18n-skip/);
  assert.match(settings, /onValueChange=\{selectLanguage\}/);
  assert.match(settings, /aria-label=\{currentLanguageLabel\}/);
  assert.match(settings, /className="ui-language-popover"/);
  assert.doesNotMatch(settings, /<select/);
  assert.doesNotMatch(settings, /onClick=\{toggleLocale\}/);
});

test("home market pulse formats visible values with the selected locale", () => {
  const home = fs.readFileSync(new URL("../components/home-page-content.tsx", import.meta.url), "utf8");
  const pulse = fs.readFileSync(new URL("../components/market-pulse-rail.tsx", import.meta.url), "utf8");
  const localeRoot = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

  assert.match(home, /t\("home\.assurancesAria"/);
  assert.match(home, /t\("home\.flow\.aria"/);
  assert.match(pulse, /const \{ t, dateLocale, formatLedgerMoney \} = useI18n\(\)/);
  assert.match(pulse, /toLocaleDateString\(dateLocale\)/);
  assert.match(pulse, /toLocaleString\(dateLocale/);
  assert.doesNotMatch(pulse, /locale === "en"/);
  assert.match(localeRoot, /"home\.pulse\.updated": "Updated \{date\}"/);
});
