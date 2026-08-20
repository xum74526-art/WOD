import type { MarketCandles, MarketHistoryProvenance } from '@/api/market'

type Translate = (key: string, params?: Record<string, string | number>) => string

const MIN_SEVEN_DAY_SPAN_HOURS = 144

function validCoverage(payload: MarketCandles) {
  const valid = (payload.candles || [])
    .map((item) => ({ start: new Date(item.start_time).getTime(), end: new Date(item.end_time).getTime() }))
    .filter((item) => Number.isFinite(item.start) && Number.isFinite(item.end))
  const days = new Set(valid.map((item) => new Date(item.start).toISOString().slice(0, 10)))
  const spanHours = valid.length
    ? (Math.max(...valid.map((item) => item.end)) - Math.min(...valid.map((item) => item.start))) / 3_600_000
    : 0
  return {
    days: Math.max(Number(payload.coverage_day_count || 0), days.size),
    spanHours: Math.max(Number(payload.coverage_span_hours || 0), spanHours),
  }
}

export function marketObservedDayCount(payload?: MarketCandles | null): number {
  return payload ? validCoverage(payload).days : 0
}

export function marketHistoryDisplayState(payload?: MarketCandles | null): 'full' | 'partial' | 'single' {
  if (!payload) return 'single'
  const declared = payload.history_state || payload.history_status
  if (declared === 'full' || declared === 'available') return 'full'
  if (declared === 'partial' || declared === 'single') return declared
  if ((payload.candles || []).length <= 1) return 'single'
  const coverage = validCoverage(payload)
  return coverage.days >= 7 && coverage.spanHours >= MIN_SEVEN_DAY_SPAN_HOURS ? 'full' : 'partial'
}

export function hasCompleteSevenDayCandles(payload?: MarketCandles | null): boolean {
  if (!payload) return false
  const rows = payload.candles || []
  if (payload.history_state === 'full' || payload.history_status === 'available' || payload.history_status === 'full') {
    return Number(payload.coverage_day_count || 0) >= 7
      && Number(payload.coverage_span_hours || 0) >= MIN_SEVEN_DAY_SPAN_HOURS
      && rows.length >= 7
  }

  // Backward-compatible fallback while older servers are still rolling out.
  const coverage = validCoverage(payload)
  return coverage.days >= 7 && coverage.spanHours >= MIN_SEVEN_DAY_SPAN_HOURS
}

function clean(value?: string | null): string {
  return String(value || '').trim()
}

export function historyProvenanceLabel(
  provenance: MarketHistoryProvenance | null | undefined,
  t: Translate,
): string {
  if (!provenance) return ''
  const provider = clean(provenance.upstream_provider) || 'Vast.ai'
  const dataset = clean(provenance.dataset_source)
  if (provenance.kind === 'external_reference') {
    return t('historyReferenceSource', { provider, dataset: dataset || t('externalDataset') })
  }
  return t('historyOfficialSource', { provider })
}
