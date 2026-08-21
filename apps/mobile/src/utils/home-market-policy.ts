export const HOME_TREND_LIMIT = 4
export const HOME_RANKING_REFRESH_MS = 10_000
export const HOME_CANDLE_REFRESH_MS = 5 * 60_000

/** Keep valid delayed quotes visible while rejecting unusable source states. */
export function isHomeMarketStatusDisplayable(status: string): boolean {
  return status === 'live' || status === 'delayed'
}

type TrendCandidate = {
  gpu_model: string
  gpu_variant: string
  sources: string[]
  volatility_sources?: string[]
  history_provenance?: {
    upstream_provider?: string
  } | null
}

export type HomeTrendRequest<T extends TrendCandidate = TrendCandidate> = {
  item: T
  sources: string[]
  billingMode: 'ondemand' | 'wod_listing'
  key: string
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
