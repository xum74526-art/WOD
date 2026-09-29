import {
  convertCardHoursToDisplay,
  convertCnyToDisplay,
  convertDisplayToCardHours,
  convertDisplayToCny,
  displayCurrencyForLocale,
  displayCurrencySymbol,
  type DisplayCurrencyConfig,
} from "./display-currency.ts";
import { financialDecimal, formatFinancialAmount } from "./financial-format.ts";
import type { KaiLocale } from "./language.ts";

type QuoteAmount = number | string | null | undefined;

const cnyCurrencies = new Set(["CNY", "RMB"]);
const ledgerCurrencies = new Set(["CH", "CARD_HOUR", "CARD_HOURS", "CARD-HOUR"]);

export function normalizeQuoteCurrency(currency: unknown): string {
  return String(currency || "")
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9._-]/g, "")
    .slice(0, 16);
}

function finite(value: QuoteAmount): number {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function financialNumber(value: number): number {
  return Number(value.toFixed(3));
}

export function formatQuoteAmountForLocale(
  amount: QuoteAmount,
  currency: unknown,
  locale: KaiLocale,
  config: DisplayCurrencyConfig,
): string {
  const code = normalizeQuoteCurrency(currency);
  const displayCode = displayCurrencyForLocale(locale);
  if (cnyCurrencies.has(code) || !code) {
    return `${displayCurrencySymbol(displayCode)}${formatFinancialAmount(convertCnyToDisplay(amount, locale, config))}`;
  }
  if (ledgerCurrencies.has(code)) {
    return `${displayCurrencySymbol(displayCode)}${formatFinancialAmount(convertCardHoursToDisplay(amount, locale, config))}`;
  }
  return `${formatFinancialAmount(amount)} ${code}`;
}

export function quoteAmountToDisplayInput(
  amount: QuoteAmount,
  currency: unknown,
  locale: KaiLocale,
  config: DisplayCurrencyConfig,
): string {
  const code = normalizeQuoteCurrency(currency);
  if (ledgerCurrencies.has(code)) return financialDecimal(convertCardHoursToDisplay(amount, locale, config));
  if (cnyCurrencies.has(code) || !code) return financialDecimal(convertCnyToDisplay(amount, locale, config));
  return financialDecimal(amount);
}

export function displayInputToQuoteAmount(
  amount: QuoteAmount,
  currency: unknown,
  locale: KaiLocale,
  config: DisplayCurrencyConfig,
): number {
  const code = normalizeQuoteCurrency(currency);
  if (ledgerCurrencies.has(code)) return financialNumber(convertDisplayToCardHours(amount, locale, config));
  if (cnyCurrencies.has(code) || !code) return financialNumber(convertDisplayToCny(amount, locale, config));
  return financialNumber(finite(amount));
}
