import { request, requestEnvelope } from './request'
import { CARD_HOUR_RATE } from '@/utils/format'

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

export type MarketHistoryState = 'available' | 'insufficient_history' | 'full' | 'partial' | 'single'

export interface MarketModel {
  gpu_model: string
  gpu_variant: string
  sources: string[]
  sample_count: number
  available_gpu_count: number
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
  available_gpu_count: number
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
    available_gpu_count: number
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
  range: string
  bucket_seconds: number
  tick_seconds: number
  method: 'observed_source_median_ohlc'
  is_interpolated: false
  requested_sources: string[]
  history_status?: MarketHistoryState
  history_state?: 'full' | 'partial' | 'single'
  coverage_day_count?: number
  coverage_span_hours?: number
  data_quality?: 'official' | 'external_reference'
  provenance?: MarketHistoryProvenance | null
  latest_live_price_cny?: number | null
  latest_live_observed_at?: string | null
  latest_live_comparable_to_history?: false
  candles: MarketCandle[]
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
  available_gpu_count: number
  source_count: number
  sources: string[]
  market_status: string
  hot_eligible: boolean
}

interface CanonicalMarketSummary {
  gpu_model: string
  gpu_slug: string
  min_price: number
  median_price: number
  average_price: number
  max_price: number
  available_gpu_count: number
  offer_count: number
  provider_count: number
  has_current_offers: boolean
  representative_provider?: string | null
  region?: string | null
  vram_gb?: number | null
  history: Array<{ date: string; median: number }>
}

function marketVariant(row: CanonicalMarketSummary) {
  return row.vram_gb ? `${row.vram_gb}GB` : ''
}

function marketStatus(row: CanonicalMarketSummary) {
  return row.has_current_offers ? 'live' : row.history.length ? 'delayed' : 'unavailable'
}

function historySpanHours(row: CanonicalMarketSummary) {
  if (row.history.length < 2) return 0
  const times = row.history.map(item => new Date(item.date).getTime()).filter(Number.isFinite)
  return times.length < 2 ? 0 : (Math.max(...times) - Math.min(...times)) / 3600000
}

function rangeWeeks(range: string): number {
  if (range === '14w' || range === '3m' || range === '30d') return 14
  if (range === '8w') return 8
  return 4
}

function historyPoints(row: CanonicalMarketSummary, count = 14) {
  return row.history.filter(point => Number(point.median) > 0).slice(0, count).reverse()
}

function historyMetrics(row: CanonicalMarketSummary, count = 4) {
  const points = historyPoints(row, count)
  const values = points.map(point => Number(point.median))
  const first = values[0]
  // Android's bundled uni-app runtime can lag behind Safari/modern browsers.
  // Avoid Array.prototype.at so the same market conversion runs on both apps.
  const last = values.length ? values[values.length - 1] : undefined
  const low = values.length ? Math.min(...values) : null
  const high = values.length ? Math.max(...values) : null
  const change = values.length >= 2 && first ? ((Number(last) - first) / first) * 100 : null
  const volatility = low != null && high != null && low > 0 ? ((high - low) / low) * 100 : null
  return { points, low, high, change, volatility }
}

function asLegacyCny(cardHours: number | null): number | null {
  return cardHours == null ? null : cardHours * CARD_HOUR_RATE
}

function fetchMarketSummary(silent = false) {
  return requestEnvelope<CanonicalMarketSummary[], { observed_at?: string; source?: string }>({
    url: '/public/market/summary',
    silent,
  })
}

export function getMarketModels(silent = false) {
  return cachedMarketRequest('models', 30_000, () => fetchMarketSummary(silent).then(({ data, meta }) => ({
    server_time: meta.observed_at || new Date().toISOString(),
    items: data.map<MarketModel>(row => {
      const metric = historyMetrics(row)
      const enough = metric.points.length >= 2
      return {
        gpu_model: row.gpu_model,
        gpu_variant: marketVariant(row),
        sources: ['getdeploying'],
        sample_count: row.offer_count,
        available_gpu_count: row.available_gpu_count,
        volatility_7d: metric.volatility,
        volatility_status: enough ? 'available' : 'insufficient_history',
        volatility_quality: enough ? 'verified' : 'limited_sample',
        history_day_count: row.history.length,
        history_point_count: row.history.length,
        history_span_hours: historySpanHours(row),
        volatility_source_count: row.provider_count,
        volatility_sources: ['getdeploying'],
        volatility_method: 'daily_median_source_range',
        change_7d_pct: metric.change,
        range_low_cny: asLegacyCny(metric.low),
        range_high_cny: asLegacyCny(metric.high),
        market_status: marketStatus(row),
      }
    }),
  })))
}

export function getLatestMarket(model: string, variant: string, sources: string[], silent = false) {
  return fetchMarketSummary(silent).then(({ data, meta }) => {
    const row = data.find(item => item.gpu_model === model) || data[0]
    if (!row) throw new Error('行情暂不可用')
    const observedAt = meta.observed_at || new Date().toISOString()
    return {
      server_time: observedAt,
      next_refresh_in: 300,
      gpu_model: row.gpu_model,
      gpu_variant: marketVariant(row),
      summary: {
        median_price_cny: asLegacyCny(row.median_price),
        min_price_cny: asLegacyCny(row.min_price),
        max_price_cny: asLegacyCny(row.max_price),
        sample_count: row.offer_count,
        available_gpu_count: row.available_gpu_count,
        source_count: row.provider_count,
      },
      items: [{
        source: 'getdeploying', source_name: 'GetDeploying', gpu_model: row.gpu_model,
        gpu_variant: marketVariant(row), billing_mode: 'ondemand', currency: 'USD',
        min_price: row.min_price, p25_price: row.min_price, median_price: row.median_price,
        p75_price: row.max_price, max_price: row.max_price, min_price_cny: asLegacyCny(row.min_price),
        median_price_cny: asLegacyCny(row.median_price), max_price_cny: asLegacyCny(row.max_price), sample_count: row.offer_count,
        available_gpu_count: row.available_gpu_count, fx_rate: null, fx_source: null,
        fx_date: null, data_quality: row.has_current_offers ? 'live' : 'historical',
        observed_at: observedAt, source_checked_at: observedAt,
      }],
      requested_source_states: { getdeploying: marketStatus(row) },
      excluded_sources: [],
    } satisfies LatestMarket
  })
}

export function getMarketHistory(model: string, variant: string, range: string, sources: string[], silent = false) {
  return fetchMarketSummary(silent).then(({ data, meta }) => {
    const row = data.find(item => item.gpu_model === model)
    return {
      server_time: meta.observed_at || new Date().toISOString(),
      gpu_model: model,
      gpu_variant: variant,
      range,
      series: row ? [{
        source: 'getdeploying', source_name: 'GetDeploying', source_status: marketStatus(row),
        points: row.history.map(point => ({
          time: point.date, price_cny: asLegacyCny(point.median), price_original: point.median,
          currency: 'USD', sample_count: 1, data_quality: 'external_reference',
        })),
      }] : [],
    } satisfies MarketHistory
  })
}

export function getMarketCandles(model: string, variant: string, range: string, sources: string[], silent = false, billingMode = 'ondemand') {
  const normalizedSources = [...new Set(sources)].sort()
  const ttlMs = 5 * 60_000
  const key = `candles|${model}|${variant}|${range}|${normalizedSources.join(',')}|${billingMode}`
  return cachedMarketRequest(key, ttlMs, () => fetchMarketSummary(silent).then(({ data, meta }) => {
    const row = data.find(item => item.gpu_model === model)
    const points = row ? historyPoints(row, rangeWeeks(range)) : []
    const candles = points.map((point, index) => {
      const previous = index === 0 ? point.median : points[index - 1].median
      const open = asLegacyCny(previous) || 0
      const close = asLegacyCny(point.median) || 0
      return {
        start_time: point.date,
        end_time: point.date,
        open_price_cny: open,
        high_price_cny: Math.max(open, close),
        low_price_cny: Math.min(open, close),
        close_price_cny: close,
        sample_count: 1,
        observation_count: 1,
        sources: ['getdeploying'],
      }
    })
    const span = points.length >= 2
      ? Math.max(0, (new Date(points[points.length - 1].date).getTime() - new Date(points[0].date).getTime()) / 3600000)
      : 0
    const state = candles.length >= 2 ? 'full' as const : candles.length ? 'single' as const : 'partial' as const
    return {
      server_time: meta.observed_at || new Date().toISOString(), gpu_model: model, gpu_variant: variant,
      billing_mode: billingMode, range, bucket_seconds: 7 * 86400, tick_seconds: 7 * 86400,
      method: 'observed_source_median_ohlc' as const, is_interpolated: false as const,
      requested_sources: ['getdeploying'], history_status: state, history_state: state,
      coverage_day_count: candles.length, coverage_span_hours: span,
      data_quality: 'external_reference' as const,
      provenance: { kind: 'external_reference' as const, dataset_source: 'GetDeploying GPU Rental Price Index', upstream_provider: 'GetDeploying', license: 'Public price index', source_url: 'https://getdeploying.com/gpu-price-index', collected_at: meta.observed_at || new Date().toISOString() },
      latest_live_price_cny: row ? asLegacyCny(row.median_price) : null,
      latest_live_observed_at: points.length ? points[points.length - 1].date : null,
      latest_live_comparable_to_history: false as const,
      candles,
    } satisfies MarketCandles
  }))
}

export function getMarketSourceStatus(silent = false) {
  return cachedMarketRequest('source-status', 8_000, () => fetchMarketSummary(silent).then(({ data, meta }) => ({
    server_time: meta.observed_at || new Date().toISOString(),
    items: [{
      source: 'getdeploying', source_name: 'GetDeploying', enabled: true,
      status: data.some(item => item.has_current_offers) ? 'live' : 'delayed',
      raw_status: 'available', refresh_seconds: 300,
      sample_count: data.reduce((sum, item) => sum + item.offer_count, 0),
      last_attempt_at: meta.observed_at || null, last_success_at: meta.observed_at || null,
      has_error: false, error_code: null,
    }],
  })))
}

export function getMarketRanking(silent = false) {
  return cachedMarketRequest('ranking', 8_000, () => fetchMarketSummary(silent).then(({ data, meta }) => ({
    server_time: meta.observed_at || new Date().toISOString(),
    items: data.map<MarketRankingItem>(row => {
      const short = historyMetrics(row, 2)
      const metric = historyMetrics(row, 4)
      const enough = metric.points.length >= 2
      return {
        gpu_model: row.gpu_model, gpu_variant: marketVariant(row), median_price_cny: asLegacyCny(row.median_price),
        change_24h: short.change, volatility_7d: metric.volatility,
        volatility_status: enough ? 'available' : 'insufficient_history',
        volatility_quality: enough ? 'verified' : 'limited_sample', history_day_count: row.history.length,
        history_point_count: row.history.length, history_span_hours: historySpanHours(row),
        volatility_source_count: row.provider_count, volatility_sources: ['getdeploying'],
        volatility_method: 'daily_median_source_range', change_7d_pct: metric.change,
        range_low_cny: asLegacyCny(metric.low), range_high_cny: asLegacyCny(metric.high), sample_count: row.offer_count,
        available_gpu_count: row.available_gpu_count, source_count: row.provider_count,
        sources: ['getdeploying'], market_status: marketStatus(row), hot_eligible: row.history.length > 1,
      }
    }),
  })))
}
