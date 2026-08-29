export const QUOTE_POLL_SECONDS = 10

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
