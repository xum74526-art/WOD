/**
 * Candle-to-candle percentage used by the chart detail card.
 * A zero result is returned only when the observed open and close are equal.
 */
export function candleChangePercent(open: number, close: number): number | null {
  if (!Number.isFinite(open) || !Number.isFinite(close) || open === 0) return null
  if (Object.is(open, close) || open === close) return 0
  return ((close / open) - 1) * 100
}

/**
 * Preserve the direction of very small real movements instead of rounding them
 * to a misleading 0%. Normal movements stay concise; only sub-display changes
 * use additional precision.
 */
export function formatSignedMarketPercentNumber(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '--'
  if (value === 0) return '0'

  const absolute = Math.abs(value)
  const digits = absolute >= 0.01 ? 2 : absolute >= 0.0001 ? 4 : 6
  const formatted = absolute < 0.000001
    ? absolute.toExponential(2)
    : absolute.toFixed(digits).replace(/\.?0+$/, '')
  return `${value > 0 ? '+' : '-'}${formatted}`
}

export function formatSignedMarketPercent(value: number | null | undefined): string {
  const number = formatSignedMarketPercentNumber(value)
  return number === '--' ? number : `${number}%`
}
