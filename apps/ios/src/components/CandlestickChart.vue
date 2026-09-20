<template>
  <view class="market-chart-shell" :class="{ compact }">
    <view v-if="loading" class="chart-loading" aria-busy="true">
      <view class="loading-line short"></view>
      <view class="loading-line"></view>
      <view class="loading-plot"></view>
    </view>
    <view v-else-if="error" class="chart-empty chart-error">
      <text class="empty-title">{{ t('chartLoadFailed') }}</text>
      <text class="empty-copy">{{ t('retry') }}</text>
    </view>
    <view v-else-if="!hasRenderableData" class="chart-empty">
      <text class="empty-title">{{ t('noVerifiedMarketData') }}</text>
      <text class="empty-copy">{{ t('noMarketDataHint') }}</text>
    </view>
    <template v-else>
      <view v-if="!compact" class="chart-toolbar">
        <view class="chart-title-wrap">
          <view class="chart-title-line">
            <text class="candlestick-label">{{ t('candlestickMode') }}</text>
            <text class="history-state-label">{{ historyStateLabel }}</text>
          </view>
          <text class="chart-price-unit">{{ displayUnitLabel }}</text>
        </view>
        <view class="latest-quote">
          <text class="latest-quote-label">{{ t(latestQuoteLabelKey) }}</text>
          <text class="latest-quote-value" :class="changeTone(headlineChange)">{{ latestReadout }}</text>
        </view>
      </view>

      <view v-if="!compact" class="market-readout">
        <view class="readout-head">
          <text class="readout-date">{{ focusedDate }}</text>
          <text
            v-if="resolvedHistoryState !== 'single'"
            class="readout-change"
            :class="changeTone(candleChange)"
          >{{ t('candleChangeValue', { value: signedChange }) }}</text>
        </view>
        <view class="ohlc-grid">
          <view v-for="item in ohlcReadout" :key="item.label" class="ohlc-item">
            <text class="ohlc-label">{{ item.label }}</text>
            <text class="ohlc-value" :class="item.tone">{{ item.value }}</text>
          </view>
        </view>
      </view>
      <view v-if="resolvedHistoryState !== 'single' && maReadout.length" class="ma-row">
        <view v-for="item in maReadout" :key="item.label" class="ma-item">
          <text class="ma-label" :style="{ color: item.color }">{{ item.label }}</text>
          <text class="ma-value" :style="{ color: item.color }">{{ item.value }}</text>
        </view>
      </view>
      <view v-if="showZoomControls" class="viewport-toolbar">
        <view class="viewport-controls">
          <view
            class="viewport-button"
            :class="{ disabled: !canZoomOut }"
            role="button"
            :aria-label="t('chartZoomOut')"
            :aria-disabled="!canZoomOut"
            @tap.stop="zoomOut"
          ><text>−</text></view>
          <text class="viewport-count">{{ t('chartPointCount', { count: visibleCandles.length }) }}</text>
          <view
            class="viewport-button"
            :class="{ disabled: !canZoomIn }"
            role="button"
            :aria-label="t('chartZoomIn')"
            :aria-disabled="!canZoomIn"
            @tap.stop="zoomIn"
          ><text>＋</text></view>
        </view>
      </view>

      <view
        :id="chartId"
        class="interactive-chart"
        :class="{ compact }"
        @touchstart="onChartTouch"
        @touchmove="onChartTouch"
        @tap="onChartTouch"
      >
        <view class="svg-box" :class="{ compact }" v-html="svgString"></view>
      </view>
      <text v-if="sourceNote && !compact" class="source-note">{{ sourceNote }}</text>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { MarketCandle, MarketCandleRange, MarketHistoryState } from '@/api/market'
import { useI18nStore } from '@/store/i18n'
import { formatNumber, toCardHours } from '@/utils/format'
import { candleChangePercent, formatSignedMarketPercent } from '@/utils/market-chart'
import {
  candleBucketMilliseconds,
  candleBodyWidth,
  candleSlotCenter,
  candleTimeGeometry,
  canSharePriceDomain,
  chartLabelIndexes,
  chartPointerIndex,
  defaultCandleZoomLimit,
  movingAverage,
  nextCandleZoomLimit,
  paddedPriceDomain,
} from '@/utils/candlestick-chart'

const i18n = useI18nStore()
const { t } = i18n
const props = withDefaults(defineProps<{
  candles: MarketCandle[]
  compact?: boolean
  sourceNote?: string
  loading?: boolean
  error?: boolean
  historyState?: MarketHistoryState | ''
  observedDays?: number
  referencePriceCny?: number | null
  referenceComparableToHistory?: boolean
  referenceSampleCount?: number
  referenceObservedAt?: string
  bucketSeconds?: number
  range?: MarketCandleRange
  displayCurrency?: 'CNY' | 'CARD_HOUR'
  zoomable?: boolean
}>(), {
  compact: false,
  sourceNote: '',
  loading: false,
  error: false,
  historyState: '',
  observedDays: 0,
  referencePriceCny: null,
  referenceComparableToHistory: false,
  referenceSampleCount: 0,
  referenceObservedAt: '',
  bucketSeconds: 0,
  range: '30d',
  displayCurrency: 'CARD_HOUR',
  zoomable: false,
})

type NormalizedCandle = MarketCandle & {
  time: number
  open: number
  high: number
  low: number
  close: number
}

const chartId = `market-chart-${Math.random().toString(36).slice(2, 10)}`
const selectedRelativeIndex = ref(0)
const cursorVisible = ref(false)
const requestedVisibleCount = ref(defaultCandleZoomLimit(props.range))
const CHART_WIDTH = 360
const DETAIL_LAYOUT = { height: 236, left: 4, right: 47, top: 12, bottom: 23 }
const COMPACT_LAYOUT = { height: 154, left: 2, right: 42, top: 8, bottom: 19 }
const visibleLimit = computed(() => props.compact
  ? 30
  : props.zoomable ? requestedVisibleCount.value : 60)

function displayPrice(value: number): number {
  return props.displayCurrency === 'CNY' ? Number(value) : toCardHours(value)
}

const displayUnitLabel = computed(() => t(props.displayCurrency === 'CNY' ? 'cnyPerGpuHour' : 'cardHourPerGpuHour'))
const referenceDisplayPrice = computed(() => props.referencePriceCny == null
  ? null
  : displayPrice(props.referencePriceCny))

const normalizedCandles = computed<NormalizedCandle[]>(() => {
  const rows = props.candles.map((item) => ({
    ...item,
    time: new Date(item.start_time).getTime(),
    open: displayPrice(item.open_price_cny),
    high: displayPrice(item.high_price_cny),
    low: displayPrice(item.low_price_cny),
    close: displayPrice(item.close_price_cny),
  }))
  .filter((item) => Number.isFinite(item.time)
    && [item.open, item.high, item.low, item.close].every(Number.isFinite)
    && item.low >= 0
    && item.high >= Math.max(item.open, item.close)
    && item.low <= Math.min(item.open, item.close))
    .sort((a, b) => a.time - b.time)

  // A comparable live observation inside the still-open bucket belongs to
  // that candle. Rendering it as only a distant horizontal line flattens the
  // whole series and hides the actual move.
  const latest = rows[rows.length - 1]
  const reference = referenceDisplayPrice.value
  const observedAt = new Date(props.referenceObservedAt || '').getTime()
  const latestEndsAt = latest ? new Date(latest.end_time).getTime() : Number.NaN
  if (latest
    && props.referenceComparableToHistory === true
    && reference != null
    && Number.isFinite(reference)
    && Number.isFinite(observedAt)
    && Number.isFinite(latestEndsAt)
    && observedAt >= latest.time
    && observedAt < latestEndsAt) {
    latest.close = reference
    latest.high = Math.max(latest.high, reference)
    latest.low = Math.min(latest.low, reference)
  }
  return rows
})

const visibleStartIndex = computed(() => Math.max(0, normalizedCandles.value.length - visibleLimit.value))
const visibleCandles = computed(() => normalizedCandles.value.slice(visibleStartIndex.value))
const showZoomControls = computed(() => props.zoomable && !props.compact && normalizedCandles.value.length > 1)
const zoomInLimit = computed(() => nextCandleZoomLimit(
  props.range,
  visibleCandles.value.length,
  normalizedCandles.value.length,
  'in',
))
const zoomOutLimit = computed(() => nextCandleZoomLimit(
  props.range,
  visibleCandles.value.length,
  normalizedCandles.value.length,
  'out',
))
const canZoomIn = computed(() => zoomInLimit.value < visibleCandles.value.length)
const canZoomOut = computed(() => zoomOutLimit.value > visibleCandles.value.length)
const focusedCandle = computed(() => visibleCandles.value[Math.max(0, Math.min(selectedRelativeIndex.value, visibleCandles.value.length - 1))])
const focusedAbsoluteIndex = computed(() => visibleStartIndex.value + Math.max(0, Math.min(selectedRelativeIndex.value, visibleCandles.value.length - 1)))
const sourceNote = computed(() => props.sourceNote)
const baselinePrice = referenceDisplayPrice
const baselineCanShareDomain = computed(() => canSharePriceDomain(
  baselinePrice.value,
  visibleCandles.value.flatMap((item) => [item.low, item.high]),
  props.referenceComparableToHistory,
))
const derivedObservedDays = computed(() => new Set(normalizedCandles.value.map((item) => (
  new Date(item.time).toISOString().slice(0, 10)
))).size)
const observedDayCount = computed(() => Math.max(Number(props.observedDays || 0), derivedObservedDays.value))
const resolvedHistoryState = computed<'full' | 'partial' | 'single'>(() => {
  if (props.historyState === 'full' || props.historyState === 'available') return 'full'
  if (props.historyState === 'single') return 'single'
  if (props.historyState === 'partial') return 'partial'
  if (normalizedCandles.value.length <= 1) return 'single'
  const expectedHours: Record<string, number> = {
    '1h': 1,
    '3h': 3,
    '6h': 6,
    '24h': 24,
    '7d': 24 * 7,
    '30d': 24 * 30,
    '90d': 24 * 90,
  }
  const expected = expectedHours[props.range]
  if (!expected) return observedDayCount.value >= 7 ? 'full' : 'partial'
  const first = normalizedCandles.value[0]
  const latest = normalizedCandles.value[normalizedCandles.value.length - 1]
  const latestEnd = new Date(latest.end_time).getTime()
  const spanHours = (Math.max(latestEnd, latest.time) - first.time) / 3_600_000
  return spanHours >= expected * 0.85 ? 'full' : 'partial'
})
const hasRenderableData = computed(() => normalizedCandles.value.length > 0 || baselinePrice.value != null)
const historyStateLabel = computed(() => resolvedHistoryState.value === 'full'
  ? t('chartFullHistory')
  : resolvedHistoryState.value === 'partial'
    ? t('chartObservedDays', { days: observedDayCount.value })
    : t('currentQuoteBaseline'))
watch(() => normalizedCandles.value.map((item) => `${item.time}:${item.close}`).join('|'), () => {
  const length = normalizedCandles.value.length
  selectedRelativeIndex.value = Math.max(0, Math.min(visibleLimit.value, length) - 1)
  cursorVisible.value = false
}, { immediate: true })
watch(() => props.range, (range) => {
  requestedVisibleCount.value = defaultCandleZoomLimit(range)
  cursorVisible.value = false
})

function applyZoom(next: number) {
  if (!showZoomControls.value || next === visibleCandles.value.length) return
  requestedVisibleCount.value = next
  selectedRelativeIndex.value = Math.max(0, Math.min(next, normalizedCandles.value.length) - 1)
  cursorVisible.value = false
}
function zoomIn() { if (canZoomIn.value) applyZoom(zoomInLimit.value) }
function zoomOut() { if (canZoomOut.value) applyZoom(zoomOutLimit.value) }

function price(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '--'
  const formatted = formatNumber(value)
  return props.displayCurrency === 'CNY' ? `¥${formatted}` : formatted
}

const focusedDate = computed(() => {
  const timestamp = focusedCandle.value?.time
    ?? (props.referenceObservedAt ? new Date(props.referenceObservedAt).getTime() : Number.NaN)
  return Number.isFinite(timestamp)
    ? new Date(timestamp).toLocaleString(i18n.locale, {
      year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
    })
    : t('currentQuoteBaseline')
})

const ohlcReadout = computed(() => {
  const item = focusedCandle.value
  if (!item) return baselinePrice.value == null
    ? []
    : [{ label: t('currentPriceShort'), value: price(baselinePrice.value), tone: 'neutral' }]
  const tone = item.close > item.open ? 'rise' : item.close < item.open ? 'fall' : 'neutral'
  return [
    { label: t('openPriceShort'), value: price(item.open), tone: 'neutral' },
    { label: t('highPriceShort'), value: price(item.high), tone: 'rise' },
    { label: t('lowPriceShort'), value: price(item.low), tone: 'fall' },
    { label: t('closePriceShort'), value: price(item.close), tone },
  ]
})

const fullMaSeries = computed(() => {
  const closes = normalizedCandles.value.map((item) => item.close)
  return [
    { period: 5, color: '#E5A229', values: movingAverage(closes, 5) },
    { period: 10, color: '#3978D4', values: movingAverage(closes, 10) },
    { period: 20, color: '#8B63C7', values: movingAverage(closes, 20) },
  ]
})
const visibleMaSeries = computed(() => fullMaSeries.value.map((item) => ({
  ...item,
  values: item.values.slice(visibleStartIndex.value),
})))
const drawableMaSeries = computed(() => visibleMaSeries.value.filter((item) => (
  item.values.filter((value): value is number => value != null).length >= 2
)))
const drawableMaPeriods = computed(() => new Set(drawableMaSeries.value.map((item) => item.period)))
const maReadout = computed(() => fullMaSeries.value.map((item) => {
  if (!drawableMaPeriods.value.has(item.period)) return null
  const value = item.values[focusedAbsoluteIndex.value]
  return value == null ? null : { label: `MA${item.period}`, color: item.color, value: price(value) }
}).filter((item): item is { label: string; color: string; value: string } => item != null))

const candleChange = computed(() => {
  const item = focusedCandle.value
  return item ? candleChangePercent(item.open, item.close) : null
})
const signedChange = computed(() => candleChange.value == null
  ? t('notAvailableShort')
  : formatSignedMarketPercent(candleChange.value))
const liveDisplayPrice = computed(() => baselinePrice.value
  ?? visibleCandles.value[visibleCandles.value.length - 1]?.close
  ?? null)
const chartHeadlinePrice = computed(() => {
  const latestClose = visibleCandles.value[visibleCandles.value.length - 1]?.close
  return baselinePrice.value != null && !baselineCanShareDomain.value && latestClose != null
    ? latestClose
    : liveDisplayPrice.value
})
const latestQuoteLabelKey = computed(() => cursorVisible.value
  || (baselinePrice.value != null && !baselineCanShareDomain.value)
  ? 'closePriceShort'
  : 'currentPriceShort')
const latestReadout = computed(() => price(cursorVisible.value
  ? focusedCandle.value?.close ?? chartHeadlinePrice.value
  : chartHeadlinePrice.value))
const headlineChange = computed(() => {
  if (cursorVisible.value) return candleChange.value
  const latest = visibleCandles.value[visibleCandles.value.length - 1]
  return latest && chartHeadlinePrice.value != null
    ? candleChangePercent(latest.open, chartHeadlinePrice.value)
    : candleChange.value
})
function changeTone(value: number | null): string {
  return value == null || value === 0 ? 'neutral' : value > 0 ? 'rise' : 'fall'
}

function eventClientX(event: any): number | null {
  const touch = event?.touches?.[0] || event?.changedTouches?.[0]
  const value = touch?.clientX ?? touch?.pageX ?? event?.clientX ?? event?.detail?.x
  return Number.isFinite(Number(value)) ? Number(value) : null
}

function onChartTouch(event: any) {
  if (props.compact) return
  const clientX = eventClientX(event)
  if (clientX == null || !hasRenderableData.value) return
  if (!visibleCandles.value.length) {
    cursorVisible.value = true
    return
  }
  uni.createSelectorQuery().select(`#${chartId}`).boundingClientRect((rect: any) => {
    if (!rect || !Number.isFinite(Number(rect.width)) || Number(rect.width) <= 0) return
    const layout = DETAIL_LAYOUT
    const plotWidth = CHART_WIDTH - layout.left - layout.right
    const geometry = candleTimeGeometry(
      visibleCandles.value.map((item) => item.time),
      layout.left,
      plotWidth,
      props.bucketSeconds,
    )
    const pointerIndex = chartPointerIndex(
      clientX,
      Number(rect.left),
      Number(rect.width),
      visibleCandles.value.length,
      CHART_WIDTH,
      layout.left,
      plotWidth,
      geometry.centers,
    )
    if (pointerIndex == null) return
    selectedRelativeIndex.value = pointerIndex
    cursorVisible.value = true
  }).exec()
}

function axisNumber(value: number, span = 1): string {
  const maximumFractionDigits = Math.abs(span) < 0.01 ? 4 : Math.abs(span) < 1 ? 3 : 2
  return formatNumber(value, { maximumFractionDigits, useGrouping: false })
}
function timeLabel(time: number): string {
  const value = new Date(time)
  const pad = (part: number) => String(part).padStart(2, '0')
  const monthDay = `${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
  const hours = `${pad(value.getHours())}:${pad(value.getMinutes())}`
  if (props.range === '1h' || props.range === '3h' || props.range === '6h') return hours
  if (props.range === '24h') return `${monthDay} ${hours}`
  return monthDay
}
function linePath(
  values: Array<number | null>,
  candles: NormalizedCandle[],
  x: (index: number) => number,
  y: (value: number) => number,
): string {
  const segments: string[] = []
  let current: string[] = []
  const effectiveBucketMs = candleBucketMilliseconds(candles.map((item) => item.time), props.bucketSeconds)
  values.forEach((value, index) => {
    const hasGap = effectiveBucketMs > 0
      && index > 0
      && candles[index].time - candles[index - 1].time > effectiveBucketMs * 1.5
    if (value == null || !Number.isFinite(value) || hasGap) {
      if (current.length > 1) segments.push(`<polyline points="${current.join(' ')}"/>`)
      current = []
      if (value == null || !Number.isFinite(value)) return
    }
    current.push(`${x(index).toFixed(1)},${y(value).toFixed(1)}`)
  })
  if (current.length > 1) segments.push(`<polyline points="${current.join(' ')}"/>`)
  return segments.join('')
}

const svgString = computed(() => {
  const candles = visibleCandles.value
  const referenceValue = candles[0]?.close ?? baselinePrice.value
  if (!candles.length && referenceValue == null) return ''
  const singleState = resolvedHistoryState.value === 'single' || candles.length <= 1
  const width = CHART_WIDTH
  const layout = props.compact ? COMPACT_LAYOUT : DETAIL_LAYOUT
  const { height, left, right, top, bottom } = layout
  const maValues = drawableMaSeries.value.flatMap((series) => series.values.filter((value): value is number => value != null))
  const marketValues = singleState
    ? [referenceValue as number]
    : candles.flatMap((item) => [item.low, item.high])
  const { min: minValue, max: maxValue } = paddedPriceDomain([
    ...marketValues,
    ...(baselinePrice.value == null || !baselineCanShareDomain.value ? [] : [baselinePrice.value]),
    ...(maValues.length ? maValues : marketValues),
  ])
  const valueRange = Math.max(maxValue - minValue, 0.000001)
  const plotWidth = width - left - right
  const plotHeight = height - top - bottom
  const timeGeometry = candleTimeGeometry(candles.map((item) => item.time), left, plotWidth, props.bucketSeconds)
  const x = (index: number) => timeGeometry.centers[index]
    ?? candleSlotCenter(index, candles.length, left, plotWidth)
  const y = (value: number) => top + (1 - (value - minValue) / valueRange) * plotHeight
  const bodyWidth = candleBodyWidth(timeGeometry.equivalentSlotCount, plotWidth, props.compact)

  const gridRowCount = props.compact ? 3 : 5
  const grid = Array.from({ length: gridRowCount }, (_, index) => {
    const ratio = index / Math.max(gridRowCount - 1, 1)
    const gy = top + ratio * plotHeight
    const label = maxValue - ratio * valueRange
    return `<line x1="${left}" y1="${gy.toFixed(1)}" x2="${width - right}" y2="${gy.toFixed(1)}" stroke="currentColor" stroke-opacity="0.09" stroke-width="0.6"/><text x="${width - right + 4}" y="${(gy + 3).toFixed(1)}" fill="currentColor" fill-opacity="0.62" font-size="${props.compact ? 8 : 9}">${axisNumber(label, valueRange)}</text>`
  }).join('')
  const verticalGrid = [1 / 3, 2 / 3].map((ratio) => {
    const gx = left + ratio * plotWidth
    return `<line x1="${gx.toFixed(1)}" y1="${top}" x2="${gx.toFixed(1)}" y2="${top + plotHeight}" stroke="currentColor" stroke-opacity="0.055" stroke-width="0.6"/>`
  }).join('')

  const market = singleState
    ? `<circle cx="${(left + plotWidth / 2).toFixed(1)}" cy="${y(referenceValue as number).toFixed(1)}" r="2.5" fill="#18AFC4" stroke="var(--card)" stroke-width="1.2" vector-effect="non-scaling-stroke"/>`
    : candles.map((item, index) => {
      const cx = x(index)
      const openY = y(item.open)
      const closeY = y(item.close)
      const rising = item.close > item.open
      const falling = item.close < item.open
      const color = rising ? '#E4474F' : falling ? '#159B68' : '#87919D'
      const fill = rising ? 'var(--card)' : color
      const bodyTop = Math.min(openY, closeY)
      const bodyHeight = Math.abs(closeY - openY)
      const wick = `<line x1="${cx.toFixed(1)}" y1="${y(item.high).toFixed(1)}" x2="${cx.toFixed(1)}" y2="${y(item.low).toFixed(1)}" stroke="${color}" stroke-width="1" vector-effect="non-scaling-stroke"/>`
      if (!rising && !falling) {
        return `${wick}<line x1="${(cx - bodyWidth / 2).toFixed(1)}" y1="${openY.toFixed(1)}" x2="${(cx + bodyWidth / 2).toFixed(1)}" y2="${openY.toFixed(1)}" stroke="${color}" stroke-width="1.4" vector-effect="non-scaling-stroke"/>`
      }
      return `${wick}<rect x="${(cx - bodyWidth / 2).toFixed(1)}" y="${bodyTop.toFixed(1)}" width="${bodyWidth.toFixed(1)}" height="${Math.max(bodyHeight, 1.3).toFixed(1)}" rx="0.4" fill="${fill}" stroke="${color}" stroke-width="1" vector-effect="non-scaling-stroke"/>`
    }).join('')

  const rawCloseTrend = (props.range === '1h' || props.range === '3h') && candles.length > 1
    ? (() => {
        const paths = linePath(candles.map((item) => item.close), candles, x, y)
        return paths
          ? `<g fill="none" stroke="#18AFC4" stroke-width="0.9" stroke-opacity="0.78" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke">${paths}</g>`
          : ''
      })()
    : ''

  const averages = singleState ? '' : drawableMaSeries.value.map((series) => {
    const paths = linePath(series.values, candles, x, y)
    return paths ? `<g fill="none" stroke="${series.color}" stroke-width="1.05" stroke-opacity="0.94" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke">${paths}</g>` : ''
  }).join('')
  const labelIndexes = chartLabelIndexes(candles.length, props.compact || candles.length < 20 ? 3 : 5)
  const dates = labelIndexes.map((index) => {
    return `<text x="${x(index).toFixed(1)}" y="${height - 5}" text-anchor="middle" fill="currentColor" fill-opacity="0.58" font-size="${props.compact ? 7.5 : 8.5}">${timeLabel(candles[index].time)}</text>`
  }).join('')

  const extremeMarks = singleState ? '' : (() => {
    const highIndex = candles.reduce((best, item, index) => item.high > candles[best].high ? index : best, 0)
    const lowIndex = candles.reduce((best, item, index) => item.low < candles[best].low ? index : best, 0)
    const mark = (index: number, value: number, high: boolean) => {
      const cx = x(index)
      const cy = y(value)
      const toRight = cx < left + plotWidth * 0.62
      const lineEnd = cx + (toRight ? 10 : -10)
      const textX = lineEnd + (toRight ? 2 : -2)
      const textY = cy + (high ? -2.5 : 8)
      return `<line x1="${cx.toFixed(1)}" y1="${cy.toFixed(1)}" x2="${lineEnd.toFixed(1)}" y2="${cy.toFixed(1)}" stroke="currentColor" stroke-opacity="0.5" stroke-width="0.7"/><text x="${textX.toFixed(1)}" y="${textY.toFixed(1)}" text-anchor="${toRight ? 'start' : 'end'}" fill="currentColor" fill-opacity="0.76" font-size="${props.compact ? 7 : 8}">${axisNumber(value, valueRange)}</text>`
    }
    return mark(highIndex, candles[highIndex].high, true) + mark(lowIndex, candles[lowIndex].low, false)
  })()

  const latestCandle = candles[candles.length - 1]
  const latestValue = baselineCanShareDomain.value
    ? baselinePrice.value ?? latestCandle?.close ?? referenceValue as number
    : latestCandle?.close ?? referenceValue as number
  const latestColor = latestCandle
    ? latestValue > latestCandle.open
      ? '#E4474F'
      : latestValue < latestCandle.open
        ? '#159B68'
        : '#18AFC4'
    : '#18AFC4'
  const latestY = y(latestValue)
  const latestChipY = Math.max(top, Math.min(top + plotHeight - 14, latestY - 7))
  const latestPriceLine = `<line x1="${left}" y1="${latestY.toFixed(1)}" x2="${width - right}" y2="${latestY.toFixed(1)}" stroke="${latestColor}" stroke-opacity="0.42" stroke-width="0.7" stroke-dasharray="3 2" vector-effect="non-scaling-stroke"/><rect x="${width - right + 2}" y="${latestChipY.toFixed(1)}" width="${right - 4}" height="14" rx="2.5" fill="${latestColor}" fill-opacity="0.13"/><text x="${width - right + 5}" y="${(latestChipY + 10).toFixed(1)}" fill="${latestColor}" font-size="${props.compact ? 8 : 9}" font-weight="700">${axisNumber(latestValue, valueRange)}</text>`

  const cursorIndex = Math.max(0, Math.min(selectedRelativeIndex.value, Math.max(candles.length - 1, 0)))
  const cursorValue = candles[cursorIndex]?.close ?? referenceValue as number
  const cursorX = singleState ? left + plotWidth / 2 : x(cursorIndex)
  const cursorY = y(cursorValue)
  const cursor = cursorVisible.value && !props.compact
    ? `<line x1="${cursorX.toFixed(1)}" y1="${top}" x2="${cursorX.toFixed(1)}" y2="${top + plotHeight}" stroke="currentColor" stroke-opacity="0.48" stroke-width="0.8" stroke-dasharray="2 2"/><line x1="${left}" y1="${cursorY.toFixed(1)}" x2="${width - right}" y2="${cursorY.toFixed(1)}" stroke="currentColor" stroke-opacity="0.38" stroke-width="0.8" stroke-dasharray="2 2"/><circle cx="${cursorX.toFixed(1)}" cy="${cursorY.toFixed(1)}" r="2.2" fill="#18AFC4" stroke="var(--card)" stroke-width="1" vector-effect="non-scaling-stroke"/>`
    : ''
  return `<svg viewBox="0 0 ${width} ${height}" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" role="img" style="font-family:system-ui,-apple-system,BlinkMacSystemFont,sans-serif;font-variant-numeric:tabular-nums"><g color="var(--text-sub)">${grid}${verticalGrid}${dates}</g>${latestPriceLine}${rawCloseTrend}${market}${averages}<g color="var(--text-sub)">${extremeMarks}</g><g color="var(--text)">${cursor}</g></svg>`
})
</script>

<style lang="scss" scoped>
.market-chart-shell {
  width: 100%;
  min-height: 590rpx;
  color: var(--text);
  --market-rise: #E4474F;
  --market-fall: #159B68;
}
.market-chart-shell.compact { min-height: 265rpx; }
.chart-toolbar { display: flex; align-items: flex-start; justify-content: space-between; gap: 20rpx; padding: 18rpx 20rpx 8rpx; }
.chart-title-wrap { min-width: 0; }
.chart-title-line { display: flex; align-items: center; gap: 12rpx; }
.candlestick-label { color: var(--text); font-size: 23rpx; font-weight: 750; white-space: nowrap; }
.history-state-label { color: var(--primary); font-size: 18rpx; font-weight: 650; white-space: nowrap; }
.chart-price-unit { display: block; color: var(--text-dim); font-size: 16rpx; margin-top: 5rpx; white-space: nowrap; }
.latest-quote { flex-shrink: 0; text-align: right; font-variant-numeric: tabular-nums; }
.latest-quote-label { display: block; color: var(--text-dim); font-size: 16rpx; }
.latest-quote-value { display: block; margin-top: 3rpx; color: var(--text); font-size: 25rpx; font-weight: 780; }
.market-readout { padding: 12rpx 20rpx 8rpx; font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif; font-variant-numeric: tabular-nums; }
.readout-head { display: flex; align-items: baseline; justify-content: space-between; gap: 16rpx; }
.readout-date { display: block; color: var(--text); font-size: 21rpx; font-weight: 700; }
.readout-change { flex-shrink: 0; font-size: 20rpx; font-weight: 750; }
.ohlc-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10rpx; margin-top: 12rpx; }
.ohlc-item { display: flex; align-items: baseline; min-width: 0; gap: 5rpx; }
.ohlc-label { flex-shrink: 0; color: var(--text-sub); font-size: 18rpx; }
.ohlc-value { min-width: 0; color: var(--text); font-size: 20rpx; font-weight: 700; overflow: hidden; text-overflow: ellipsis; }
.rise, .ohlc-value.rise { color: var(--market-rise); }
.fall, .ohlc-value.fall { color: var(--market-fall); }
.neutral { color: var(--text-sub); }
.ma-row { display: flex; align-items: center; gap: 18rpx; min-height: 40rpx; padding: 0 20rpx; overflow: hidden; font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif; font-variant-numeric: tabular-nums; }
.compact .ma-row { min-height: 30rpx; padding: 0 8rpx; }
.ma-item { display: flex; align-items: center; min-width: 0; gap: 5rpx; }
.ma-label { font-size: 17rpx; font-weight: 700; }
.ma-value { font-size: 17rpx; font-weight: 650; white-space: nowrap; }
.compact .ma-label, .compact .ma-value { font-size: 15rpx; }
.viewport-toolbar { display: flex; justify-content: flex-end; min-height: 68rpx; padding: 2rpx 20rpx 6rpx; }
.viewport-controls { display: inline-grid; grid-template-columns: 68rpx minmax(82rpx, auto) 68rpx; align-items: stretch; min-height: 60rpx; overflow: hidden; border: 1rpx solid var(--border); border-radius: 12rpx; background: var(--card); box-shadow: 0 4rpx 16rpx rgba(15, 32, 48, 0.06); }
.viewport-button { display: flex; align-items: center; justify-content: center; color: var(--text); font-size: 32rpx; font-weight: 600; background: var(--card); }
.viewport-button:first-child { border-right: 1rpx solid var(--divider); }
.viewport-button:last-child { border-left: 1rpx solid var(--divider); }
.viewport-button:active { background: var(--primary-soft); }
.viewport-button.disabled { color: var(--text-dim); opacity: 0.34; }
.viewport-count { display: flex; align-items: center; justify-content: center; padding: 0 12rpx; color: var(--text-sub); font-size: 18rpx; font-variant-numeric: tabular-nums; white-space: nowrap; }
.interactive-chart { position: relative; width: 100%; height: auto; aspect-ratio: 360 / 236; overflow: hidden; color: var(--text-sub); touch-action: pan-y; }
.interactive-chart.compact { height: auto; aspect-ratio: 360 / 154; }
.svg-box { position: absolute; inset: 0; width: 100%; height: 100%; }
.source-note { display: block; padding: 2rpx 20rpx 14rpx; color: var(--text-dim); font-size: 16rpx; line-height: 1.35; }
.chart-empty { min-height: 500rpx; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 24rpx; text-align: center; }
.compact .chart-empty { min-height: 250rpx; }
.chart-error .empty-title { color: var(--down); }
.empty-title { color: var(--text); font-size: 28rpx; font-weight: 600; }
.empty-copy { color: var(--text-sub); font-size: 22rpx; margin-top: 10rpx; }
.chart-loading { min-height: 540rpx; padding: 26rpx 20rpx; }
.compact .chart-loading { min-height: 250rpx; padding: 14rpx 8rpx; }
.loading-line, .loading-plot { background: var(--divider); border-radius: 10rpx; }
.loading-line { width: 70%; height: 24rpx; margin-top: 14rpx; }
.loading-line.short { width: 34%; }
.loading-plot { height: 400rpx; margin-top: 28rpx; }
.compact .loading-line { height: 16rpx; margin-top: 8rpx; }
.compact .loading-plot { height: 174rpx; margin-top: 14rpx; }
@media (max-width: 520px) {
  .chart-toolbar { align-items: flex-start; }
  .latest-quote-value { font-size: 23rpx; }
  .ohlc-grid { gap: 7rpx; }
  .ohlc-label { font-size: 17rpx; }
  .ohlc-value { font-size: 18rpx; }
}
</style>
