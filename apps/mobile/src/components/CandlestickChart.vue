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
      <view class="chart-toolbar">
        <text class="merged-chart-label">{{ t('mergedMarketChart') }}</text>
        <view class="viewport-controls">
          <view class="viewport-button" :class="{ disabled: normalizedCandles.length <= 1 }" role="button" :aria-disabled="normalizedCandles.length <= 1" :aria-label="t('chartMoveOlder')" @tap="moveWindow(-1)">‹</view>
          <view class="viewport-button" :class="{ disabled: normalizedCandles.length <= 1 }" role="button" :aria-disabled="normalizedCandles.length <= 1" :aria-label="t('chartZoomOut')" @tap="zoom(-1)">−</view>
          <text class="viewport-count">{{ t('chartPointCount', { count: displayPointCount }) }}</text>
          <view class="viewport-button" :class="{ disabled: normalizedCandles.length <= 1 }" role="button" :aria-disabled="normalizedCandles.length <= 1" :aria-label="t('chartZoomIn')" @tap="zoom(1)">+</view>
          <view class="viewport-button" :class="{ disabled: normalizedCandles.length <= 1 }" role="button" :aria-disabled="normalizedCandles.length <= 1" :aria-label="t('chartMoveNewer')" @tap="moveWindow(1)">›</view>
        </view>
      </view>

      <view class="history-state-row">
        <text class="history-state-label">{{ historyStateLabel }}</text>
        <text class="history-state-help">{{ historyStateHelp }}</text>
      </view>

      <view class="market-readout">
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
      <view v-if="resolvedHistoryState !== 'single'" class="ma-row">
        <view class="ma-item price-line-item">
          <view class="ma-line" :style="{ backgroundColor: '#18AFC4' }"></view>
          <text class="ma-label">{{ t('priceTrendLine') }}</text>
          <text class="ma-value" :style="{ color: '#18AFC4' }">{{ priceTrendReadout }}</text>
        </view>
        <view v-for="item in maReadout" :key="item.label" class="ma-item">
          <view class="ma-line" :style="{ backgroundColor: item.color }"></view>
          <text class="ma-label">{{ item.label }}</text>
          <text class="ma-value" :style="{ color: item.color }">{{ item.value }}</text>
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
        <view v-if="cursorVisible && (focusedCandle || baselinePrice != null)" class="cursor-card" :class="{ right: selectedRelativeIndex < visibleCandles.length / 2 }">
          <text class="cursor-date">{{ focusedDate }}</text>
          <view v-if="focusedCandle" class="cursor-grid">
            <text>{{ t('openPriceShort') }} {{ price(focusedCandle.open) }}</text>
            <text>{{ t('highPriceShort') }} {{ price(focusedCandle.high) }}</text>
            <text>{{ t('lowPriceShort') }} {{ price(focusedCandle.low) }}</text>
            <text>{{ t('closePriceShort') }} {{ price(focusedCandle.close) }}</text>
          </view>
          <view v-else class="cursor-grid single-price">
            <text>{{ t('currentPriceShort') }} {{ price(baselinePrice) }}</text>
          </view>
          <view class="cursor-foot">
            <text v-if="resolvedHistoryState !== 'single'" :class="changeTone(candleChange)">{{ t('candleChangeValue', { value: signedChange }) }}</text>
            <text v-else>{{ t('currentQuoteBaseline') }}</text>
            <text>{{ t('realQuoteSamples', { count: focusedSampleCount }) }}</text>
          </view>
        </view>
      </view>
      <text v-if="sourceNote" class="source-note">{{ sourceNote }}</text>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { MarketCandle, MarketHistoryState } from '@/api/market'
import { useI18nStore } from '@/store/i18n'
import { formatNumber, toCardHours } from '@/utils/format'
import { candleChangePercent, formatSignedMarketPercent } from '@/utils/market-chart'

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
  referenceSampleCount?: number
  referenceObservedAt?: string
}>(), {
  compact: false,
  sourceNote: '',
  loading: false,
  error: false,
  historyState: '',
  observedDays: 0,
  referencePriceCny: null,
  referenceSampleCount: 0,
  referenceObservedAt: '',
})

type NormalizedCandle = MarketCandle & {
  time: number
  open: number
  high: number
  low: number
  close: number
}

const chartId = `market-chart-${Math.random().toString(36).slice(2, 10)}`
const viewportSize = ref(0)
const viewportEnd = ref(0)
const selectedRelativeIndex = ref(0)
const cursorVisible = ref(false)

const normalizedCandles = computed<NormalizedCandle[]>(() => props.candles
  .map((item) => ({
    ...item,
    time: new Date(item.start_time).getTime(),
    open: toCardHours(item.open_price_cny),
    high: toCardHours(item.high_price_cny),
    low: toCardHours(item.low_price_cny),
    close: toCardHours(item.close_price_cny),
  }))
  .filter((item) => Number.isFinite(item.time) && [item.open, item.high, item.low, item.close].every(Number.isFinite))
  .sort((a, b) => a.time - b.time))

const viewportBounds = computed(() => {
  const total = normalizedCandles.value.length
  const size = Math.max(1, Math.min(viewportSize.value || total, total))
  const end = Math.max(size, Math.min(viewportEnd.value || total, total))
  return { start: end - size, end, size }
})
const visibleCandles = computed(() => normalizedCandles.value.slice(viewportBounds.value.start, viewportBounds.value.end))
const focusedCandle = computed(() => visibleCandles.value[Math.max(0, Math.min(selectedRelativeIndex.value, visibleCandles.value.length - 1))])
const focusedAbsoluteIndex = computed(() => viewportBounds.value.start + Math.max(0, Math.min(selectedRelativeIndex.value, visibleCandles.value.length - 1)))
const sourceNote = computed(() => props.sourceNote)
const baselinePrice = computed(() => props.referencePriceCny == null
  ? null
  : toCardHours(props.referencePriceCny))
const derivedObservedDays = computed(() => new Set(normalizedCandles.value.map((item) => (
  new Date(item.time).toISOString().slice(0, 10)
))).size)
const observedDayCount = computed(() => Math.max(Number(props.observedDays || 0), derivedObservedDays.value))
const resolvedHistoryState = computed<'full' | 'partial' | 'single'>(() => {
  if (props.historyState === 'full' || props.historyState === 'available') return 'full'
  if (props.historyState === 'single') return 'single'
  if (props.historyState === 'partial') return 'partial'
  if (normalizedCandles.value.length <= 1) return 'single'
  return observedDayCount.value >= 7 ? 'full' : 'partial'
})
const hasRenderableData = computed(() => normalizedCandles.value.length > 0 || baselinePrice.value != null)
const displayPointCount = computed(() => Math.max(visibleCandles.value.length, hasRenderableData.value ? 1 : 0))
const historyStateLabel = computed(() => resolvedHistoryState.value === 'full'
  ? t('chartFullHistory')
  : resolvedHistoryState.value === 'partial'
    ? t('chartObservedDays', { days: observedDayCount.value })
    : t('currentQuoteBaseline'))
const historyStateHelp = computed(() => resolvedHistoryState.value === 'single'
  ? t('chartBaselineHint')
  : t('chartExploreHint'))
const focusedSampleCount = computed(() => focusedCandle.value?.sample_count ?? props.referenceSampleCount ?? 0)

watch(() => normalizedCandles.value.length, (length) => {
  viewportSize.value = Math.min(length, 30)
  viewportEnd.value = length
  selectedRelativeIndex.value = Math.max(0, Math.min(viewportSize.value, length) - 1)
  cursorVisible.value = false
}, { immediate: true })

function price(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? '--' : formatNumber(value)
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

function movingAverage(values: number[], period: number): Array<number | null> {
  let running = 0
  return values.map((value, index) => {
    running += value
    if (index >= period) running -= values[index - period]
    return index + 1 >= period ? running / period : null
  })
}

const fullMaSeries = computed(() => {
  const closes = normalizedCandles.value.map((item) => item.close)
  return [
    { period: 5, color: '#2878E3', values: movingAverage(closes, 5) },
    { period: 10, color: '#D97706', values: movingAverage(closes, 10) },
    { period: 20, color: '#0F9EA8', values: movingAverage(closes, 20) },
  ]
})
const visibleMaSeries = computed(() => fullMaSeries.value.map((item) => ({
  ...item,
  values: item.values.slice(viewportBounds.value.start, viewportBounds.value.end),
})))
const maReadout = computed(() => fullMaSeries.value.map((item) => {
  const value = item.values[focusedAbsoluteIndex.value]
  return { label: `MA${item.period}`, color: item.color, value: value == null ? t('marketHistoryShort') : price(value) }
}))
const priceTrendReadout = computed(() => price(focusedCandle.value?.close ?? baselinePrice.value))

const candleChange = computed(() => {
  const item = focusedCandle.value
  return item ? candleChangePercent(item.open, item.close) : null
})
const signedChange = computed(() => candleChange.value == null
  ? t('notAvailableShort')
  : formatSignedMarketPercent(candleChange.value))
function changeTone(value: number | null): string {
  return value == null || value === 0 ? 'neutral' : value > 0 ? 'rise' : 'fall'
}

function zoom(direction: 1 | -1) {
  const total = normalizedCandles.value.length
  if (total <= 1) return
  const step = Math.max(1, Math.round(viewportBounds.value.size * 0.25))
  const minimum = Math.min(5, total)
  viewportSize.value = direction > 0
    ? Math.max(minimum, viewportBounds.value.size - step)
    : Math.min(total, viewportBounds.value.size + step)
  viewportEnd.value = Math.max(viewportSize.value, Math.min(viewportEnd.value, total))
  selectedRelativeIndex.value = Math.max(0, visibleCandles.value.length - 1)
  cursorVisible.value = false
}

function moveWindow(direction: 1 | -1) {
  const total = normalizedCandles.value.length
  const step = Math.max(1, Math.round(viewportBounds.value.size / 3))
  viewportEnd.value = direction < 0
    ? Math.max(viewportBounds.value.size, viewportBounds.value.end - step)
    : Math.min(total, viewportBounds.value.end + step)
  selectedRelativeIndex.value = Math.max(0, visibleCandles.value.length - 1)
  cursorVisible.value = false
}

function eventClientX(event: any): number | null {
  const touch = event?.touches?.[0] || event?.changedTouches?.[0]
  const value = touch?.clientX ?? touch?.pageX ?? event?.clientX ?? event?.detail?.x
  return Number.isFinite(Number(value)) ? Number(value) : null
}

function onChartTouch(event: any) {
  const clientX = eventClientX(event)
  if (clientX == null || !hasRenderableData.value) return
  if (!visibleCandles.value.length) {
    cursorVisible.value = true
    return
  }
  uni.createSelectorQuery().select(`#${chartId}`).boundingClientRect((rect: any) => {
    if (!rect || !Number.isFinite(Number(rect.width)) || Number(rect.width) <= 0) return
    const ratio = Math.max(0, Math.min(1, (clientX - Number(rect.left)) / Number(rect.width)))
    selectedRelativeIndex.value = Math.round(ratio * Math.max(visibleCandles.value.length - 1, 0))
    cursorVisible.value = true
  }).exec()
}

function axisNumber(value: number): string {
  return formatNumber(value, { maximumFractionDigits: 2, useGrouping: false })
}
function timeLabel(time: number): string {
  return new Date(time).toLocaleDateString(i18n.locale, { month: 'numeric', day: 'numeric' })
}
function linePath(values: Array<number | null>, x: (index: number) => number, y: (value: number) => number): string {
  const segments: string[] = []
  let current: string[] = []
  values.forEach((value, index) => {
    if (value == null || !Number.isFinite(value)) {
      if (current.length > 1) segments.push(`<polyline points="${current.join(' ')}"/>`)
      current = []
      return
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
  const width = 680
  const height = props.compact ? 250 : 340
  const left = 12
  const right = 66
  const top = 12
  const bottom = 36
  const maValues = visibleMaSeries.value.flatMap((series) => series.values.filter((value): value is number => value != null))
  const marketValues = singleState
    ? [referenceValue as number]
    : candles.flatMap((item) => [item.low, item.high])
  const rawMin = Math.min(...marketValues, ...(maValues.length ? maValues : marketValues))
  const rawMax = Math.max(...marketValues, ...(maValues.length ? maValues : marketValues))
  const padding = Math.max((rawMax - rawMin) * 0.1, rawMax * 0.012, 0.01)
  const minValue = Math.max(0, rawMin - padding)
  const maxValue = rawMax + padding
  const valueRange = Math.max(maxValue - minValue, 0.000001)
  const plotWidth = width - left - right
  const plotHeight = height - top - bottom
  const x = (index: number) => candles.length <= 1 ? left + plotWidth / 2 : left + (index / (candles.length - 1)) * plotWidth
  const y = (value: number) => top + (1 - (value - minValue) / valueRange) * plotHeight
  const bodyWidth = Math.max(5, Math.min(props.compact ? 12 : 20, plotWidth / Math.max(candles.length, 1) * 0.62))

  const grid = Array.from({ length: 4 }, (_, index) => {
    const ratio = index / 3
    const gy = top + ratio * plotHeight
    const label = maxValue - ratio * valueRange
    return `<line x1="${left}" y1="${gy.toFixed(1)}" x2="${width - right}" y2="${gy.toFixed(1)}" stroke="currentColor" stroke-opacity="0.11" stroke-width="1"/><text x="${width - right + 8}" y="${(gy + 4).toFixed(1)}" fill="currentColor" fill-opacity="0.68" font-size="15">${axisNumber(label)}</text>`
  }).join('')

  const market = singleState
    ? `<line x1="${left}" y1="${y(referenceValue as number).toFixed(1)}" x2="${width - right}" y2="${y(referenceValue as number).toFixed(1)}" stroke="#18AFC4" stroke-width="1.8" vector-effect="non-scaling-stroke"/><circle cx="${(left + plotWidth / 2).toFixed(1)}" cy="${y(referenceValue as number).toFixed(1)}" r="4" fill="#18AFC4" stroke="var(--card)" stroke-width="2"/>`
    : candles.map((item, index) => {
      const cx = x(index)
      const openY = y(item.open)
      const closeY = y(item.close)
      const rising = item.close > item.open
      const falling = item.close < item.open
      const color = rising ? '#E5484D' : falling ? '#16A36A' : '#7B8794'
      // Chinese market convention: rising candles are red and hollow,
      // falling candles are green and solid.  A genuine flat candle remains
      // a neutral doji instead of being given a fabricated direction.
      const fill = rising ? 'var(--card)' : color
      const bodyTop = Math.min(openY, closeY)
      const bodyHeight = Math.max(Math.abs(closeY - openY), 2)
      return `<line x1="${cx.toFixed(1)}" y1="${y(item.high).toFixed(1)}" x2="${cx.toFixed(1)}" y2="${y(item.low).toFixed(1)}" stroke="${color}" stroke-width="1.4" vector-effect="non-scaling-stroke"/><rect x="${(cx - bodyWidth / 2).toFixed(1)}" y="${bodyTop.toFixed(1)}" width="${bodyWidth.toFixed(1)}" height="${bodyHeight.toFixed(1)}" rx="1" fill="${fill}" stroke="${color}" stroke-width="1.4" vector-effect="non-scaling-stroke"/>`
    }).join('')

  const priceTrend = singleState ? '' : (() => {
    const paths = linePath(candles.map((item) => item.close), x, y)
    return paths ? `<g fill="none" stroke="#18AFC4" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke">${paths}</g>` : ''
  })()
  const averages = singleState ? '' : visibleMaSeries.value.map((series) => {
    const paths = linePath(series.values, x, y)
    return paths ? `<g fill="none" stroke="${series.color}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round">${paths}</g>` : ''
  }).join('')
  const labelIndexes = candles.length ? [...new Set([0, Math.floor((candles.length - 1) / 2), candles.length - 1])] : []
  const dates = labelIndexes.map((index) => {
    const anchor = index === 0 ? 'start' : index === candles.length - 1 ? 'end' : 'middle'
    return `<text x="${x(index).toFixed(1)}" y="${height - 7}" text-anchor="${anchor}" fill="currentColor" fill-opacity="0.68" font-size="15">${timeLabel(candles[index].time)}</text>`
  }).join('')
  const cursorIndex = Math.max(0, Math.min(selectedRelativeIndex.value, Math.max(candles.length - 1, 0)))
  const cursorValue = candles[cursorIndex]?.close ?? referenceValue as number
  const cursorX = singleState ? left + plotWidth / 2 : x(cursorIndex)
  const cursor = cursorVisible.value
    ? `<line x1="${cursorX.toFixed(1)}" y1="${top}" x2="${cursorX.toFixed(1)}" y2="${top + plotHeight}" stroke="currentColor" stroke-opacity="0.48" stroke-width="1"/><line x1="${left}" y1="${y(cursorValue).toFixed(1)}" x2="${width - right}" y2="${y(cursorValue).toFixed(1)}" stroke="currentColor" stroke-opacity="0.36" stroke-width="1"/><circle cx="${cursorX.toFixed(1)}" cy="${y(cursorValue).toFixed(1)}" r="4" fill="#18AFC4" stroke="var(--card)" stroke-width="2"/>`
    : ''
  return `<svg viewBox="0 0 ${width} ${height}" width="100%" height="100%" preserveAspectRatio="none" role="img" style="font-family:Arial,sans-serif"><g color="var(--text-sub)">${grid}${dates}</g>${market}${priceTrend}${averages}<g color="var(--text)">${cursor}</g></svg>`
})
</script>

<style lang="scss" scoped>
.market-chart-shell { width: 100%; min-height: 550rpx; color: var(--text); }
.market-chart-shell.compact { min-height: 430rpx; }
.chart-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16rpx; padding: 14rpx 18rpx 6rpx; }
.merged-chart-label { color: var(--text); font-size: 21rpx; font-weight: 750; white-space: nowrap; }
.viewport-controls { display: flex; align-items: center; gap: 5rpx; }
.viewport-button { width: 46rpx; height: 46rpx; display: flex; align-items: center; justify-content: center; color: var(--text); border: 1rpx solid var(--border); border-radius: 8rpx; background: var(--card); font-size: 28rpx; line-height: 1; }
.viewport-button:active { transform: scale(0.96); }
.viewport-button.disabled { opacity: 0.34; }
.viewport-count { min-width: 50rpx; color: var(--text-sub); font-size: 17rpx; text-align: center; }
.history-state-row { display: flex; align-items: baseline; justify-content: space-between; gap: 14rpx; padding: 4rpx 20rpx 6rpx; }
.history-state-label { flex-shrink: 0; color: var(--primary); font-size: 19rpx; font-weight: 700; }
.history-state-help { color: var(--text-sub); font-size: 17rpx; line-height: 1.35; text-align: right; }
.market-readout { padding: 12rpx 20rpx 8rpx; font-family: Arial, sans-serif; font-variant-numeric: tabular-nums; }
.readout-head { display: flex; align-items: baseline; justify-content: space-between; gap: 16rpx; }
.readout-date { display: block; color: var(--text); font-size: 21rpx; font-weight: 700; }
.readout-change { flex-shrink: 0; font-size: 20rpx; font-weight: 750; }
.ohlc-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10rpx; margin-top: 12rpx; }
.ohlc-item { display: flex; align-items: baseline; min-width: 0; gap: 5rpx; }
.ohlc-label { flex-shrink: 0; color: var(--text-sub); font-size: 18rpx; }
.ohlc-value { min-width: 0; color: var(--text); font-size: 20rpx; font-weight: 700; overflow: hidden; text-overflow: ellipsis; }
.rise, .ohlc-value.rise { color: #C9363E; }
.fall, .ohlc-value.fall { color: #168A5B; }
.neutral { color: var(--text-sub); }
.ma-row { display: flex; align-items: center; gap: 14rpx; min-height: 42rpx; padding: 0 20rpx; overflow: hidden; font-family: Arial, sans-serif; font-variant-numeric: tabular-nums; }
.ma-item { display: flex; align-items: center; min-width: 0; gap: 5rpx; }
.price-line-item { flex-shrink: 0; }
.ma-line { width: 18rpx; height: 3rpx; flex-shrink: 0; }
.ma-label { color: var(--text-sub); font-size: 17rpx; }
.ma-value { font-size: 18rpx; font-weight: 700; white-space: nowrap; }
.interactive-chart { position: relative; width: 100%; height: 340rpx; overflow: hidden; color: var(--text-sub); touch-action: pan-y; }
.interactive-chart.compact { height: 250rpx; }
.svg-box { width: 100%; height: 100%; }
.cursor-card { position: absolute; top: 14rpx; left: 16rpx; width: 246rpx; padding: 14rpx 16rpx; border: 1rpx solid var(--border); border-radius: 12rpx; background: var(--card); box-shadow: 0 8rpx 30rpx var(--card-border); color: var(--text); font-family: Arial, sans-serif; font-variant-numeric: tabular-nums; pointer-events: none; }
.cursor-card.right { left: auto; right: 16rpx; }
.cursor-date { display: block; color: var(--text); font-size: 19rpx; font-weight: 700; }
.cursor-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5rpx 12rpx; margin-top: 9rpx; color: var(--text-sub); font-size: 17rpx; }
.cursor-grid.single-price { grid-template-columns: 1fr; color: var(--text); font-weight: 700; }
.cursor-foot { display: flex; justify-content: space-between; gap: 8rpx; margin-top: 9rpx; padding-top: 8rpx; border-top: 1rpx solid var(--divider); color: var(--text-sub); font-size: 17rpx; }
.source-note { display: block; padding: 6rpx 20rpx 16rpx; color: var(--text-sub); font-size: 18rpx; line-height: 1.4; }
.chart-empty { min-height: 500rpx; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 24rpx; text-align: center; }
.chart-error .empty-title { color: var(--down); }
.empty-title { color: var(--text); font-size: 28rpx; font-weight: 600; }
.empty-copy { color: var(--text-sub); font-size: 22rpx; margin-top: 10rpx; }
.chart-loading { min-height: 500rpx; padding: 26rpx 20rpx; }
.loading-line, .loading-plot { background: var(--divider); border-radius: 10rpx; }
.loading-line { width: 70%; height: 24rpx; margin-top: 14rpx; }
.loading-line.short { width: 34%; }
.loading-plot { height: 330rpx; margin-top: 28rpx; }
@media (max-width: 520px) {
  .chart-toolbar { align-items: stretch; flex-direction: column; }
  .merged-chart-label { align-self: flex-start; }
  .viewport-controls { width: 100%; justify-content: space-between; }
  .history-state-row { align-items: flex-start; flex-direction: column; gap: 4rpx; }
  .history-state-help { text-align: left; }
}
</style>
