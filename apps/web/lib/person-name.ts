import { pinyin } from "pinyin-pro";
import type { KaiLocale } from "./language.ts";
import { toTraditionalChinese } from "./traditional-chinese.ts";

const PERSON_EN: Record<string, string> = {
  "体验用户": "Demo User",
};

const PLATFORM_MARKET_NAMES = new Set([
  "WOD资讯",
  "ZTW资讯",
  "ZTW資訊",
  "KAI星算资讯",
  "KAI星算資訊",
  "KAI星算平台行情",
  "算力星圖平台行情",
]);

/**
 * Localize a Chinese personal name for display only. Callers must keep the
 * original server value in editable form state and write that raw value back
 * unless the user explicitly changes it.
 */
export function localizePersonName(value: string | null | undefined, locale: KaiLocale) {
  const source = String(value ?? "").trim();
  if (PLATFORM_MARKET_NAMES.has(source) && locale === "zh-Hans") return "KAI星算平台行情";
  if (PLATFORM_MARKET_NAMES.has(source) && locale === "zh-Hant") return "算力星圖平台行情";
  if (PLATFORM_MARKET_NAMES.has(source) && locale === "en") return "KAI星算 Platform Market";
  if (source && locale === "zh-Hant") return toTraditionalChinese(source);
  if (!source || locale !== "en") return source;
  if (PERSON_EN[source]) return PERSON_EN[source];
  if (!/^[\u3400-\u9fff·]{2,12}$/.test(source)) return source;

  const words = pinyin(source, { toneType: "none", type: "array" }).filter(Boolean);
  if (!words.length) return source;
  const surname = words[0].charAt(0).toUpperCase() + words[0].slice(1);
  const given = words.slice(1).join("");
  return given ? `${surname} ${given.charAt(0).toUpperCase()}${given.slice(1)}` : surname;
}

export function personNameInputValue(value: string, locale: KaiLocale, edited: boolean) {
  return edited ? value : localizePersonName(value, locale);
}

export function personNameSaveValue(serverValue: string | null | undefined, draftValue: string, edited: boolean) {
  return (edited ? draftValue : serverValue || draftValue).trim();
}
