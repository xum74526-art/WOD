import {
  cnyToDisplayCurrency,
  displayCurrencyToCny,
  formatCardHourCurrency,
  formatCnyCurrency,
} from './format.ts'

type QuoteAmount = number | string | null | undefined

function quoteNumber(amount: QuoteAmount, minimumDigits: number, maximumDigits: number): string {
  const numeric = Number(amount)
  const safe = Number.isFinite(numeric) ? numeric : 0
  const scale = 10 ** maximumDigits
  const rounded = Math.round((safe + Number.EPSILON) * scale) / scale
  const parts = rounded.toFixed(maximumDigits).split('.')
  let fraction = parts[1] || ''
  while (fraction.length > minimumDigits && fraction.endsWith('0')) fraction = fraction.slice(0, -1)
  const integer = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${integer}${fraction ? `.${fraction}` : ''}`
}

export function normalizeQuoteCurrency(currency: unknown): string {
  return String(currency || '')
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9._-]/g, '')
    .slice(0, 16)
}

export function formatQuoteAmount(
  amount: QuoteAmount,
  currency: unknown,
  cardHourLabel: string,
): string {
  const code = normalizeQuoteCurrency(currency)
  if (code === 'CNY' || code === 'RMB') return formatCnyCurrency(amount)
  if (['CH', 'CARD_HOUR', 'CARD_HOURS', 'CARD-HOUR'].includes(code)) {
    return formatCardHourCurrency(amount)
  }
  void cardHourLabel
  return `${quoteNumber(amount, 3, 3)} ${code || '—'}`
}

function usesLedgerCurrency(code: string): boolean {
  return code === 'CNY' || code === 'RMB' || ['CH', 'CARD_HOUR', 'CARD_HOURS', 'CARD-HOUR'].includes(code)
}

/** Convert a stored CNY/legacy-ledger quote into the amount shown in the current language. */
export function quoteAmountToDisplayInput(amount: QuoteAmount, currency: unknown): string {
  const code = normalizeQuoteCurrency(currency)
  const numeric = usesLedgerCurrency(code) || !code ? cnyToDisplayCurrency(amount) : Number(amount)
  return (Number.isFinite(numeric) ? numeric : 0).toFixed(3)
}

/** Convert the current language's quote input back to canonical CNY before submission. */
export function displayInputToQuoteAmount(amount: QuoteAmount, currency: unknown): number {
  const code = normalizeQuoteCurrency(currency)
  const numeric = Number(amount)
  if (!Number.isFinite(numeric)) return 0
  const stored = usesLedgerCurrency(code) || !code ? displayCurrencyToCny(numeric) : numeric
  return Number(stored.toFixed(3))
}
