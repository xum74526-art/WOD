export const MARKET_PUBLICATION_SECONDS = 5 * 60
export const MARKET_PUBLICATION_MS = MARKET_PUBLICATION_SECONDS * 1000
export const QUOTE_POLL_SECONDS = MARKET_PUBLICATION_SECONDS

type MarketObservation = {
  observed_at?: string | null
}

export function latestMarketObservationMs(items: MarketObservation[]): number {
  return items.reduce((latest, item) => {
    const raw = item.observed_at
    const value = raw ? new Date(raw).getTime() : Number.NaN
    return Number.isFinite(value) ? Math.max(latest, value) : latest
  }, 0)
}

export function hasAdvancedMarketObservation(previous: number, items: MarketObservation[]): boolean {
  const current = latestMarketObservationMs(items)
  return current > 0 && current > previous
}

export function marketCandlesNeedRefresh(
  previousObservationMs: number,
  items: MarketObservation[],
  candleObservedAt?: string | null,
): boolean {
  if (previousObservationMs <= 0) return false
  const currentObservationMs = latestMarketObservationMs(items)
  if (currentObservationMs <= previousObservationMs) return false
  const candleObservationMs = candleObservedAt ? new Date(candleObservedAt).getTime() : 0
  return !Number.isFinite(candleObservationMs) || candleObservationMs < currentObservationMs
}
