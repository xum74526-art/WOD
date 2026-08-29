export function movingAverage(values: number[], period: number): Array<number | null> {
  if (!Number.isInteger(period) || period <= 0) return values.map(() => null)
  let running = 0
  return values.map((value, index) => {
    running += value
    if (index >= period) running -= values[index - period]
    return index + 1 >= period ? running / period : null
  })
}

export function candleSlotCenter(index: number, count: number, left: number, plotWidth: number): number {
  if (count <= 0) return left + plotWidth / 2
  return left + ((Math.max(0, Math.min(index, count - 1)) + 0.5) / count) * plotWidth
}

export function candleBucketMilliseconds(times: number[], bucketSeconds = 0): number {
  if (bucketSeconds > 0) return bucketSeconds * 1000
  const gaps = times.slice(1)
    .map((value, index) => value - times[index])
    .filter((value) => Number.isFinite(value) && value > 0)
    .sort((a, b) => a - b)
  if (!gaps.length) return 0
  const middle = Math.floor(gaps.length / 2)
  return gaps.length % 2 === 0
    ? (gaps[middle - 1] + gaps[middle]) / 2
    : gaps[middle]
}

export function candleTimeGeometry(
  times: number[],
  left: number,
  plotWidth: number,
  bucketSeconds = 0,
): { centers: number[]; equivalentSlotCount: number } {
  if (!times.length) return { centers: [], equivalentSlotCount: 1 }
  if (times.length === 1) return { centers: [left + plotWidth / 2], equivalentSlotCount: 1 }
  const gaps = times.slice(1).map((value, index) => value - times[index]).filter((value) => value > 0)
  if (!gaps.length) {
    return {
      centers: times.map((_, index) => candleSlotCenter(index, times.length, left, plotWidth)),
      equivalentSlotCount: times.length,
    }
  }
  const bucket = candleBucketMilliseconds(times, bucketSeconds)
  const first = times[0]
  const span = Math.max(times[times.length - 1] - first + bucket, bucket)
  return {
    centers: times.map((value) => left + ((value - first + bucket / 2) / span) * plotWidth),
    equivalentSlotCount: Math.max(times.length, span / bucket),
  }
}

export function candleBodyWidth(count: number, plotWidth: number, compact = false): number {
  const slotWidth = plotWidth / Math.max(count, 1)
  const minimum = compact ? 3.2 : 2.6
  const maximum = compact ? 8 : 9
  const ratio = compact ? 0.48 : 0.56
  return Math.max(minimum, Math.min(maximum, slotWidth * ratio))
}

export function chartLabelIndexes(count: number, maximumLabels: number): number[] {
  if (!Number.isInteger(count) || count <= 0 || !Number.isInteger(maximumLabels) || maximumLabels <= 0) return []
  const labelCount = Math.min(count, maximumLabels)
  if (labelCount === 1) return [0]
  return [...new Set(Array.from({ length: labelCount }, (_, index) => (
    Math.round((index / (labelCount - 1)) * (count - 1))
  )))]
}

export function canSharePriceDomain(
  reference: number | null,
  historyValues: number[],
  explicitlyComparable = false,
): boolean {
  if (reference == null || !Number.isFinite(reference)) return false
  const finite = historyValues.filter(Number.isFinite)
  if (!finite.length) return true
  return explicitlyComparable
}

export function chartPointerIndex(
  clientX: number,
  rectLeft: number,
  rectWidth: number,
  candleCount: number,
  viewBoxWidth: number,
  plotLeft: number,
  plotWidth: number,
  candleCenters: number[] = [],
): number | null {
  if (!Number.isFinite(clientX) || !Number.isFinite(rectLeft) || rectWidth <= 0 || candleCount <= 0) return null
  const localX = ((clientX - rectLeft) / rectWidth) * viewBoxWidth
  if (localX < plotLeft || localX > plotLeft + plotWidth) return null
  if (candleCenters.length === candleCount) {
    return candleCenters.reduce((best, value, index) => (
      Math.abs(value - localX) < Math.abs(candleCenters[best] - localX) ? index : best
    ), 0)
  }
  if (candleCount === 1) return 0
  const ratio = Math.max(0, Math.min(0.999999, (localX - plotLeft) / plotWidth))
  return Math.max(0, Math.min(candleCount - 1, Math.floor(ratio * candleCount)))
}

export function paddedPriceDomain(values: number[]): { min: number; max: number } {
  const finite = values.filter(Number.isFinite)
  if (!finite.length) return { min: 0, max: 1 }
  const rawMin = Math.min(...finite)
  const rawMax = Math.max(...finite)
  const span = rawMax - rawMin
  const padding = span > 0
    ? Math.max(span * 0.12, Math.abs(rawMax) * 0.000001, 0.000001)
    : Math.max(Math.abs(rawMax) * 0.003, 0.01)
  return {
    min: Math.max(0, rawMin - padding),
    max: rawMax + padding,
  }
}

export type CandleZoomDirection = 'in' | 'out'

const CANDLE_ZOOM_CONFIG: Record<string, { steps: number[]; defaultLimit: number }> = {
  '24h': { steps: [12, 18, 24, 36, 48, 60], defaultLimit: 36 },
  '7d': { steps: [14, 21, 28, 42, 60], defaultLimit: 42 },
  '30d': { steps: [15, 20, 30, 45, 60], defaultLimit: 45 },
}
const DEFAULT_CANDLE_ZOOM = { steps: [12, 18, 24, 36, 48, 60], defaultLimit: 60 }

function candleZoomConfig(range: string) {
  return CANDLE_ZOOM_CONFIG[range] || DEFAULT_CANDLE_ZOOM
}

export function defaultCandleZoomLimit(range: string, compact = false): number {
  return compact ? 30 : candleZoomConfig(range).defaultLimit
}

export function nextCandleZoomLimit(
  range: string,
  currentVisible: number,
  total: number,
  direction: CandleZoomDirection,
): number {
  const available = Math.max(0, Math.min(Math.floor(total), 60))
  if (available <= 1) return available
  const current = Math.max(1, Math.min(Math.floor(currentVisible), available))
  const steps = candleZoomConfig(range).steps
  if (direction === 'in') {
    const next = [...steps].reverse().find((value) => value < current)
    return Math.min(next ?? current, available)
  }
  const next = steps.find((value) => value > current)
  return Math.min(next ?? available, available)
}
