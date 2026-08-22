export interface MarketRangeMetric {
  gpu_model?: string
  gpu_variant?: string
  change_7d_pct?: number | null
  range_low_cny?: number | null
  range_high_cny?: number | null
  history_day_count?: number
  history_span_hours?: number
}

export interface MarketListProduct {
  id: number
  gpu_model: string
  memory: string
  stock?: number
  price?: number
  status?: string
  purchasable?: boolean
}

export type MarketRangeMap = Record<string, MarketRangeMetric>

export function gpuMarketKey(model: string, variant = ''): string {
  return `${String(model || '').replace(/\s+/g, '').toUpperCase()}|${String(variant || '').replace(/\s+/g, '').toUpperCase()}`
}

export function hasCompleteSevenDayMetric(metric?: MarketRangeMetric | null): boolean {
  if (!metric || Number(metric.history_day_count || 0) < 7 || Number(metric.history_span_hours || 0) < 144) return false
  return trustedSevenDayChange(metric) != null && trustedSevenDayPriceRange(metric) != null
}

/** 百分比只取后端给出的七日涨跌，不用价格横截面代算。 */
export function trustedSevenDayChange(metric?: MarketRangeMetric | null): number | null {
  const value = Number(metric?.change_7d_pct)
  return Number.isFinite(value) ? value : null
}

/** 价格区间只取后端同口径的七日最低/最高价。 */
export function trustedSevenDayPriceRange(metric?: MarketRangeMetric | null): { low: number; high: number } | null {
  const low = Number(metric?.range_low_cny)
  const high = Number(metric?.range_high_cny)
  return Number.isFinite(low) && Number.isFinite(high) && low >= 0 && high >= low ? { low, high } : null
}

export function buildMarketRangeMap(items: MarketRangeMetric[]): MarketRangeMap {
  const ranges: MarketRangeMap = {}
  for (const item of items) {
    const key = gpuMarketKey(item.gpu_model || '', item.gpu_variant)
    const existing = ranges[key]
    const itemScore = hasCompleteSevenDayMetric(item) ? Math.abs(trustedSevenDayChange(item) || 0) : -1
    const existingScore = hasCompleteSevenDayMetric(existing) ? Math.abs(trustedSevenDayChange(existing) || 0) : -1
    if (!existing || itemScore > existingScore) {
      ranges[key] = item
    }
  }
  return ranges
}

export function compareMarketPriority(
  a: MarketListProduct,
  b: MarketListProduct,
  ranges: MarketRangeMap,
): number {
  const aMetric = ranges[gpuMarketKey(a.gpu_model, a.memory)]
  const bMetric = ranges[gpuMarketKey(b.gpu_model, b.memory)]
  const av = hasCompleteSevenDayMetric(aMetric) ? Math.abs(trustedSevenDayChange(aMetric) || 0) : null
  const bv = hasCompleteSevenDayMetric(bMetric) ? Math.abs(trustedSevenDayChange(bMetric) || 0) : null
  if (av == null && bv == null) return Number(b.stock || 0) - Number(a.stock || 0)
  if (av == null) return 1
  if (bv == null) return -1
  return bv - av || Number(b.stock || 0) - Number(a.stock || 0)
}

export function sortByMarketPriority<T extends MarketListProduct>(items: T[], ranges: MarketRangeMap): T[] {
  return [...items].sort((a, b) => compareMarketPriority(a, b, ranges))
}

/**
 * Pick a small, useful homepage set without making the product list depend on
 * seven complete days of market history.  Verified market movement still
 * decides the order when it exists; live stock is the deterministic fallback
 * while an external history source is unavailable.
 */
export function selectFeaturedProducts<T extends MarketListProduct>(
  items: T[],
  ranges: MarketRangeMap,
  limit = 4,
): T[] {
  const maximum = Math.max(0, limit)
  if (!maximum) return []
  const eligible = items
    .filter((item) => item.status !== 'off')
    .filter((item) => item.price == null || (Number.isFinite(Number(item.price)) && Number(item.price) > 0))
    .filter((item) => item.stock == null || Number(item.stock) > 0)
    .sort((a, b) => {
      const purchasePriority = Number(Boolean(b.purchasable)) - Number(Boolean(a.purchasable))
      return purchasePriority || compareMarketPriority(a, b, ranges)
    })

  const selected: T[] = []
  const selectedIds = new Set<number>()
  const models = new Set<string>()
  for (const item of eligible) {
    const model = gpuMarketKey(item.gpu_model).split('|')[0]
    if (models.has(model)) continue
    selected.push(item)
    selectedIds.add(item.id)
    models.add(model)
    if (selected.length >= maximum) return selected
  }
  for (const item of eligible) {
    if (selectedIds.has(item.id)) continue
    selected.push(item)
    if (selected.length >= maximum) break
  }
  return selected
}

export function mergeUniqueProducts<T extends { id: number }>(current: T[], incoming: T[]): T[] {
  const seen = new Set(current.map((item) => item.id))
  return current.concat(incoming.filter((item) => !seen.has(item.id) && seen.add(item.id)))
}
