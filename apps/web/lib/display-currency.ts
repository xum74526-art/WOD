import { formatFinancialAmount } from "./financial-format.ts";
import type { KaiLocale } from "./language.ts";

export type DisplayCurrencyCode = "CNY" | "HKD" | "USD";
export type DisplayCurrencyConfig = {
  base_currency: "CNY";
  settlement_currency: "CNY";
  fraction_digits: 3;
  card_hour_cny_rate: number;
  rates: Record<DisplayCurrencyCode, number>;
  rate_mode: "daily_reference";
  rate_source: string;
  rate_date: string | null;
  rates_stale: boolean;
  conversion_scope: "display_only";
};

export const DEFAULT_DISPLAY_CURRENCY_CONFIG: DisplayCurrencyConfig = Object.freeze({
  base_currency: "CNY",
  settlement_currency: "CNY",
  fraction_digits: 3,
  card_hour_cny_rate: 1,
  rates: Object.freeze({ CNY: 1, HKD: 1.169032900251, USD: 0.149020326907 }),
  rate_mode: "daily_reference",
  rate_source: "ECB_BOOTSTRAP",
  rate_date: "2026-09-28",
  rates_stale: true,
  conversion_scope: "display_only",
});

/** Immutable historical conversion used only while rendering old text. */
export const LEGACY_CARD_HOUR_CNY_RATE = 1.002;

export function displayCurrencyForLocale(locale: KaiLocale): DisplayCurrencyCode {
  if (locale === "en") return "USD";
  return locale === "zh-Hant" ? "HKD" : "CNY";
}

export function displayCurrencySymbol(currency: DisplayCurrencyCode): string {
  if (currency === "HKD") return "HK$";
  if (currency === "USD") return "US$";
  return "¥";
}

function finite(value: number | string | null | undefined): number {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

export function convertCnyToDisplay(
  value: number | string | null | undefined,
  locale: KaiLocale,
  config: DisplayCurrencyConfig = DEFAULT_DISPLAY_CURRENCY_CONFIG,
): number {
  const currency = displayCurrencyForLocale(locale);
  const rate = finite(config.rates[currency]);
  return finite(value) * (rate > 0 ? rate : 1);
}

export function convertDisplayToCny(
  value: number | string | null | undefined,
  locale: KaiLocale,
  config: DisplayCurrencyConfig = DEFAULT_DISPLAY_CURRENCY_CONFIG,
): number {
  const currency = displayCurrencyForLocale(locale);
  const rate = finite(config.rates[currency]);
  return finite(value) / (rate > 0 ? rate : 1);
}

export function normalizeDisplayInputToCny(
  value: number | string | null | undefined,
  locale: KaiLocale,
  config: DisplayCurrencyConfig = DEFAULT_DISPLAY_CURRENCY_CONFIG,
  options: { fractionDigits?: number; displayFractionDigits?: number; minimum?: number; maximum?: number } = {},
): number {
  const fractionDigits = Math.max(0, Math.min(options.fractionDigits ?? 3, 6));
  const displayFractionDigits = Math.max(0, Math.min(options.displayFractionDigits ?? 3, 6));
  const raw = convertDisplayToCny(value, locale, config);
  const halfDisplayStep = 0.5 * (10 ** -displayFractionDigits);
  const tolerance = Math.abs(convertDisplayToCny(halfDisplayStep, locale, config)) + Number.EPSILON;
  if (Number.isFinite(options.minimum) && raw < Number(options.minimum) && Number(options.minimum) - raw <= tolerance) {
    return Number(options.minimum);
  }
  if (Number.isFinite(options.maximum) && raw > Number(options.maximum) && raw - Number(options.maximum) <= tolerance) {
    return Number(options.maximum);
  }
  return Number(raw.toFixed(fractionDigits));
}

export function legacyCardHoursToCny(value: number | string | null | undefined): number {
  return finite(value) * LEGACY_CARD_HOUR_CNY_RATE;
}

export function formatLegacyCardHoursForLocale(
  value: number | string | null | undefined,
  locale: KaiLocale,
  config: DisplayCurrencyConfig = DEFAULT_DISPLAY_CURRENCY_CONFIG,
): string {
  return formatCnyForLocale(legacyCardHoursToCny(value), locale, config);
}

export function convertCardHoursToDisplay(
  value: number | string | null | undefined,
  locale: KaiLocale,
  config: DisplayCurrencyConfig = DEFAULT_DISPLAY_CURRENCY_CONFIG,
): number {
  return convertCnyToDisplay(value, locale, config);
}

export function convertDisplayToCardHours(
  value: number | string | null | undefined,
  locale: KaiLocale,
  config: DisplayCurrencyConfig = DEFAULT_DISPLAY_CURRENCY_CONFIG,
): number {
  return convertDisplayToCny(value, locale, config);
}

export function formatCnyForLocale(
  value: number | string | null | undefined,
  locale: KaiLocale,
  config: DisplayCurrencyConfig = DEFAULT_DISPLAY_CURRENCY_CONFIG,
): string {
  const currency = displayCurrencyForLocale(locale);
  return `${displayCurrencySymbol(currency)}${formatFinancialAmount(convertCnyToDisplay(value, locale, config))}`;
}

export function formatCardHoursForLocale(
  value: number | string | null | undefined,
  locale: KaiLocale,
  config: DisplayCurrencyConfig = DEFAULT_DISPLAY_CURRENCY_CONFIG,
): string {
  const currency = displayCurrencyForLocale(locale);
  return `${displayCurrencySymbol(currency)}${formatFinancialAmount(convertCardHoursToDisplay(value, locale, config))}`;
}
