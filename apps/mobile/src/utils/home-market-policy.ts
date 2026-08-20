export const HOME_TREND_LIMIT = 4
export const HOME_RANKING_REFRESH_MS = 60_000
export const HOME_CANDLE_REFRESH_MS = 5 * 60_000

type TrendCandidate = {
  gpu_model: string
  gpu_variant: string
  sources: string[]
  volatility_sources?: string[]
  history_provenance?: {
    upstream_provider?: string
  } | null
}

type RankedTrendCandidate = TrendCandidate & {
  median_price_cny: number | null
  sample_count: number
  market_status: string
  hot_eligible?: boolean
  history_day_count?: number
}

export type HomeTrendRequest<T extends TrendCandidate = TrendCandidate> = {
  item: T
  sources: string[]
  billingMode: 'ondemand' | 'wod_listing'
  key: string
}

/**
 * Prefer currently quoted models, but keep attributed historical price-index
 * rows as a truthful fallback when the upstream snapshot has no live offers.
 * An empty live marketplace must not hide an otherwise usable market history.
 */
export function selectHomeTrendCandidates<T extends RankedTrendCandidate>(items: T[]): T[] {
  const quoted = items.filter((item) => (
    item.market_status !== 'unavailable'
    && Number.isFinite(Number(item.median_price_cny))
    && Number(item.median_price_cny) > 0
  ))
  const live = quoted.filter((item) => item.market_status === 'live' && item.sample_count > 0)
  const historical = quoted.filter((item) => (
    item.market_status !== 'live'
    && (item.hot_eligible || Number(item.history_day_count || 0) > 1)
  ))
  return live.concat(historical)
}

/**
 * Turn already-ranked, complete-history items into a bounded request plan.
 * Historical provenance wins over a current WOD listing source: the chart
 * must ask for the attributed Vast archive rather than probe unrelated WOD
 * snapshots and then fan out through fallback candidates.
 */
export function buildHomeTrendRequests<T extends TrendCandidate>(
  candidates: T[],
  limit = HOME_TREND_LIMIT,
): HomeTrendRequest<T>[] {
  const requests: HomeTrendRequest<T>[] = []
  const seen = new Set<string>()
  for (const item of candidates) {
    const key = `${item.gpu_model.replace(/\s+/g, '').toUpperCase()}|${item.gpu_variant.replace(/\s+/g, '').toUpperCase()}`
    if (seen.has(key)) continue
    let sources: string[] = []
    if (item.history_provenance?.upstream_provider === 'vast') {
      sources = ['vast']
    } else {
      sources = (item.volatility_sources || []).filter((source) => source === 'vast' || source === 'autodl')
      if (!sources.length) sources = item.sources.filter((source) => source !== 'wod')
      if (!sources.length && item.sources.includes('wod')) sources = ['wod']
    }
    sources = [...new Set(sources)].sort()
    if (!sources.length) continue
    requests.push({
      item,
      sources,
      billingMode: sources.every((source) => source === 'wod') ? 'wod_listing' : 'ondemand',
      key,
    })
    seen.add(key)
    if (requests.length >= Math.max(limit, 0)) break
  }
  return requests
}
