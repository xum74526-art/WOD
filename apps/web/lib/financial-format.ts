export const FINANCIAL_FRACTION_DIGITS = 3;

export type FinancialValue = number | string | null | undefined;

function finiteFinancialValue(value: FinancialValue): number {
  const number = Number(value ?? 0);
  return Number.isFinite(number) ? (Object.is(number, -0) ? 0 : number) : 0;
}

/**
 * Canonical user-facing precision for CNY amounts, exchange rates and
 * product prices. Calculations keep their original precision; only the value
 * shown to users is rounded to exactly three decimal places.
 */
export function formatFinancialAmount(
  value: FinancialValue,
  locale = "zh-CN",
  useGrouping = true,
): string {
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: FINANCIAL_FRACTION_DIGITS,
    maximumFractionDigits: FINANCIAL_FRACTION_DIGITS,
    useGrouping,
  }).format(finiteFinancialValue(value));
}

/** Locale-neutral fixed-point string for Web view-model contracts. */
export function financialDecimal(value: FinancialValue): string {
  return finiteFinancialValue(value).toFixed(FINANCIAL_FRACTION_DIGITS);
}
