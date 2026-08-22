export const HOME_TREND_LIMIT = 4
export const HOME_RANKING_REFRESH_MS = 10_000
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

export type HomeTrendRequest<T extends TrendCandidate = TrendCandidate> = {
  item: T
  sources: string[]
  billingMode: 'ondemand'
  key: string
}

/**
 * Turn already-ranked KAI items into a bounded request plan. Historical rows
 * from retired providers remain displayable elsewhere but never generate a
 * current quote request.
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
    const historyProvider = String(item.history_provenance?.upstream_provider || '').trim().toLowerCase().replace(/[\s._-]+/g, '')
    const sources = [...new Set([...(item.sources || []), ...(item.volatility_sources || [])])]
      .map((source) => String(source || '').trim().toLowerCase())
    const hasKai = sources.includes('kai')
      || ['kai', 'kaipricing', 'pricingkaicom'].includes(historyProvider)
    if (!hasKai) continue
    requests.push({
      item,
      sources: ['kai'],
      billingMode: 'ondemand',
      key,
    })
    seen.add(key)
    if (requests.length >= Math.max(limit, 0)) break
  }
  return requests
}
