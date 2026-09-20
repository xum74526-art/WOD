export type KaiLocale = "zh-Hant" | "zh-Hans" | "en";

export const DEFAULT_LOCALE: KaiLocale = "zh-Hant";
export const LOCALE_ORDER: readonly KaiLocale[] = ["zh-Hant", "zh-Hans", "en"];

export function normalizeStoredLocale(value: unknown): KaiLocale {
  if (value === "en") return "en";
  if (value === "zh-Hans") return "zh-Hans";
  if (value === "zh-Hant" || value === "zh-TW" || value === "zh-HK") return "zh-Hant";
  // Previous Web releases stored their only Chinese option as `zh-CN` (or
  // occasionally `zh`). Treat that legacy value as the new primary language.
  // A user who explicitly selects Simplified Chinese now stores `zh-Hans`.
  return DEFAULT_LOCALE;
}

export function localeForFormatting(locale: KaiLocale): "zh-TW" | "zh-CN" | "en-US" {
  if (locale === "en") return "en-US";
  return locale === "zh-Hant" ? "zh-TW" : "zh-CN";
}

export function nextLocale(locale: KaiLocale): KaiLocale {
  const index = LOCALE_ORDER.indexOf(locale);
  return LOCALE_ORDER[(index + 1) % LOCALE_ORDER.length];
}

export function supportApiLanguage(locale: KaiLocale): "zh" | "en" {
  return locale === "en" ? "en" : "zh";
}
