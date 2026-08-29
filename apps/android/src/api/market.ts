import { request } from './request'

type TimedMarketValue = { expiresAt: number; value: unknown }
const marketResponseCache = new Map<string, TimedMarketValue>()
const marketRequestsInFlight = new Map<string, Promise<unknown>>()

function cachedMarketRequest<T>(key: string, ttlMs: number, loader: () => Promise<T>): Promise<T> {
  const now = Date.now()
  const cached = marketResponseCache.get(key)
  if (cached && cached.expiresAt > now) return Promise.resolve(cached.value as T)
  const running = marketRequestsInFlight.get(key)
  if (running) return running as Promise<T>
  const pending = loader()
    .then((value) => {
      marketResponseCache.set(key, { expiresAt: Date.now() + ttlMs, value })
      if (marketResponseCache.size > 80) {
        for (const [entryKey, entry] of marketResponseCache) {
          if (entry.expiresAt <= Date.now()) marketResponseCache.delete(entryKey)
        }
      }
      return value
    })
    .finally(() => { marketRequestsInFlight.delete(key) })
  marketRequestsInFlight.set(key, pending)
  return pending
}

export interface MarketHistoryProvenance {
  kind: 'official' | 'external_reference'
  dataset_source: string
  upstream_provider: string
  license: string
  source_url: string
  collected_at: string
}

export type MarketHistoryState = 'available' | 'insufficient_history' | 'partial_history' | 'single_observation' | 'unavailable' | 'full' | 'partial' | 'single'

export interface MarketModel {
  gpu_model: string
  gpu_variant: string
  sources: string[]
  sample_count: number
  available_gpu_count: number | null
  volatility_7d: number | null
  volatility_status: 'available' | 'insufficient_history'
  volatility_quality: 'verified' | 'limited_sample'
  history_day_count: number
  history_point_count: number
  history_span_hours: number
  volatility_source_count: number
  volatility_sources: string[]
  volatility_method: 'daily_median_source_range'
  change_7d_pct?: number | null
  range_low_cny?: number | null
  range_high_cny?: number | null
  history_min_daily_sample_count?: number
  history_provenance?: MarketHistoryProvenance | null
  market_status: string
}

export interface MarketSnapshot {
  source: string
  source_name: string
  gpu_model: string
  gpu_variant: string
  billing_mode: string
  currency: string
  min_price: number
  p25_price: number
  median_price: number
  p75_price: number
  max_price: number
  min_price_cny: number | null
  median_price_cny: number | null
  max_price_cny: number | null
  sample_count: number
  available_gpu_count: number | null
  fx_rate: number | null
  fx_source: string | null
  fx_date: string | null
  data_quality: string
  observed_at: string
  source_checked_at: string | null
}

export interface LatestMarket {
  server_time: string
  next_refresh_in: number
  gpu_model: string
  gpu_variant: string
  summary: {
    median_price_cny: number | null
    min_price_cny: number | null
    max_price_cny: number | null
    sample_count: number
    available_gpu_count: number | null
    source_count: number
  }
  items: MarketSnapshot[]
  requested_source_states: Record<string, string>
  excluded_sources: string[]
}

export interface HistoryPoint {
  time: string
  price_cny: number | null
  price_original: number
  currency: string
  sample_count: number
  data_quality: string
}

export interface MarketSeries {
  source: string
  source_name: string
  source_status: string
  points: HistoryPoint[]
}

export interface MarketHistory {
  server_time: string
  gpu_model: string
  gpu_variant: string
  range: string
  series: MarketSeries[]
}

export type MarketCandleRange = '1h' | '3h' | '6h' | '24h' | '7d' | '30d'
export type MarketCandleApiRange = MarketCandleRange
export type MarketQuoteRange = Extract<MarketCandleApiRange, '24h' | '7d' | '30d'>

export interface MarketCandle {
  start_time: string
  end_time: string
  open_price_cny: number
  high_price_cny: number
  low_price_cny: number
  close_price_cny: number
  sample_count: number
  observation_count: number
  sources: string[]
}

export interface MarketCandles {
  server_time: string
  gpu_model: string
  gpu_variant: string
  billing_mode: string
  range: MarketCandleApiRange
  bucket_seconds: number
  tick_seconds: number
  method: 'observed_source_median_ohlc'
  is_interpolated: false
  requested_sources: string[]
  history_status?: MarketHistoryState
  history_state?: 'full' | 'partial' | 'single'
  curve_status?: 'full' | 'partial' | 'single' | 'unavailable'
  coverage_class?: 'full' | 'partial' | 'single' | 'unavailable'
  coverage_day_count?: number
  coverage_span_hours?: number
  data_quality?: 'official' | 'external_reference'
  provenance?: MarketHistoryProvenance | null
  latest_live_price_cny?: number | null
  latest_live_observed_at?: string | null
  latest_live_comparable_to_history?: boolean | null
  candles: MarketCandle[]
}

export interface MarketCandlesParams {
  external_product_id?: string | null
  force_refresh?: boolean
}

export interface MarketSourceState {
  source: string
  source_name: string
  enabled: boolean
  status: string
  raw_status: string
  refresh_seconds: number
  sample_count: number
  last_attempt_at: string | null
  last_success_at: string | null
  has_error: boolean
  error_code: 'credentials_missing' | 'authentication_failed' | 'rate_limited' | 'upstream_timeout' | 'upstream_error' | null
}

export interface MarketRankingItem {
  gpu_model: string
  gpu_variant: string
  median_price_cny: number | null
  min_price_cny?: number | null
  max_price_cny?: number | null
  p25_price_cny?: number | null
  p75_price_cny?: number | null
  change_24h: number | null
  volatility_7d: number | null
  volatility_status: 'available' | 'insufficient_history'
  volatility_quality: 'verified' | 'limited_sample'
  history_day_count: number
  history_point_count: number
  history_span_hours: number
  volatility_source_count: number
  volatility_sources: string[]
  volatility_method: 'daily_median_source_range'
  change_7d_pct?: number | null
  range_low_cny?: number | null
  range_high_cny?: number | null
  history_min_daily_sample_count?: number
  history_provenance?: MarketHistoryProvenance | null
  sample_count: number
  quote_sample_count?: number
  available_gpu_count: number | null
  region_count?: number
  source_count: number
  sources: string[]
  market_status: string
  hot_eligible: boolean
}

function activeMarketSources(sources: string[]): string[] {
  const hasKai = sources.some((source) => {
    const normalized = String(source || '').trim().toLowerCase().replace(/[\s._-]+/g, '')
    return normalized === 'kai' || normalized === 'kaipricing' || normalized === 'pricingkaicom'
  })
  if (!hasKai) throw new Error('KAI market source is required')
  return ['kai']
}

export function getMarketModels(silent = false) {
  return cachedMarketRequest('models', 30_000, () => (
    request<{ server_time: string; items: MarketModel[] }>({ url: '/market/models', silent })
  ))
}

export function getLatestMarket(model: string, variant: string, sources: string[], silent = false) {
  const activeSources = activeMarketSources(sources)
  return request<LatestMarket>({
    url: '/market/prices/latest',
    data: { model, variant, sources: activeSources.join(',') },
    silent,
  })
}

export function getMarketHistory(model: string, variant: string, range: string, sources: string[], silent = false) {
  const activeSources = activeMarketSources(sources)
  return request<MarketHistory>({
    url: '/market/prices/history',
    data: { model, variant, range, sources: activeSources.join(',') },
    silent,
  })
}

export function getMarketCandles(
  model: string,
  variant: string,
  range: MarketCandleApiRange,
  sources: string[],
  silent = false,
  billingMode = 'ondemand',
  params: MarketCandlesParams = {},
) {
  const normalizedSources = activeMarketSources(sources)
  const externalProductId = String(params.external_product_id || '').trim()
  const ttlMs = range === '7d' || range === '30d' ? 5 * 60_000 : range === '24h' ? 30_000 : 8_000
  const key = `candles|${model}|${variant}|${range}|${normalizedSources.join(',')}|${billingMode}|${encodeURIComponent(externalProductId)}`
  if (params.force_refresh) marketResponseCache.delete(key)
  return cachedMarketRequest(key, ttlMs, () => (
    request<MarketCandles>({
      url: '/market/prices/candles',
      data: {
        model,
        variant,
        range,
        sources: normalizedSources.join(','),
        billing_mode: billingMode,
        ...(externalProductId ? { external_product_id: externalProductId } : {}),
      },
      silent,
    })
  ))
}

export function getMarketSourceStatus(silent = false) {
  return cachedMarketRequest('source-status', 8_000, () => (
    request<{ server_time: string; items: MarketSourceState[] }>({ url: '/market/sources/status', silent })
  ))
}

export function getMarketRanking(silent = false) {
  return cachedMarketRequest('ranking', 8_000, () => (
    request<{ server_time: string; items: MarketRankingItem[] }>({ url: '/market/ranking', silent })
  ))
}
