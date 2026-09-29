<template>
  <view class="market-chart" :class="{ compact }">
    <view v-if="!hasPoints" class="chart-empty">
      <text class="empty-title">{{ t('noVerifiedMarketData') }}</text>
      <text class="empty-copy">{{ t('noMarketDataHint') }}</text>
    </view>
    <view v-else class="svg-box" :class="{ compact }" v-html="svgString"></view>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { MarketSeries } from '@/api/market'
import { useI18nStore } from '@/store/i18n'
import { cnyToDisplayCurrency, displayCurrencySymbol, formatAmount } from '@/utils/format'

const i18n = useI18nStore()
const { t } = i18n
const props = withDefaults(defineProps<{
  series: MarketSeries[]
  compact?: boolean
}>(), {
  compact: false,
})
const compact = computed(() => props.compact)

const palette: Record<string, { color: string }> = {
  wod: { color: '#18AFC4' },
  autodl: { color: '#2774D8' },
  kai: { color: '#0F9F8F' },
  vast: { color: '#D97706' },
}

const validSeries = computed(() => props.series
  .map((series) => ({
    ...series,
    points: series.points.filter((point) => point.price_cny != null && Number.isFinite(Number(point.price_cny))),
  }))
  .filter((series) => series.points.length))

const hasPoints = computed(() => validSeries.value.length > 0)

function formatAxis(value: number): string {
  const formatted = formatAmount(value, false)
  return `${displayCurrencySymbol()}${formatted}`
}

function displayPrice(value: number | null): number {
  const numericValue = Number(value)
  return cnyToDisplayCurrency(numericValue)
}

function formatTimeLabel(time: number, span: number): string {
  const date = new Date(time)
  if (span >= 48 * 60 * 60 * 1000) {
    return date.toLocaleDateString(i18n.locale, { month: 'numeric', day: 'numeric' })
  }
  return date.toLocaleTimeString(i18n.locale, { hour: '2-digit', minute: '2-digit' })
}

const svgString = computed(() => {
  const all = validSeries.value.flatMap((series) => series.points.map((point) => ({
    time: new Date(point.time).getTime(),
    value: displayPrice(point.price_cny),
  }))).filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value))
  if (!all.length) return ''

  const width = 640
  const height = props.compact ? 176 : 340
  const left = props.compact ? 52 : 60
  const right = 14
  const top = 12
  const bottom = props.compact ? 24 : 36
  const rawMin = Math.min(...all.map((point) => point.value))
  const rawMax = Math.max(...all.map((point) => point.value))
  const padding = Math.max((rawMax - rawMin) * 0.12, rawMax * 0.025, 0.01)
  const minValue = Math.max(0, rawMin - padding)
  const maxValue = rawMax + padding
  const valueRange = Math.max(maxValue - minValue, 0.000001)
  const minTime = Math.min(...all.map((point) => point.time))
  const maxTime = Math.max(...all.map((point) => point.time))
  const timeRange = Math.max(maxTime - minTime, 1)
  const x = (time: number) => left + ((time - minTime) / timeRange) * (width - left - right)
  const y = (value: number) => top + (1 - (value - minValue) / valueRange) * (height - top - bottom)

  const grid = Array.from({ length: 4 }, (_, index) => {
    const ratio = index / 3
    const gy = top + ratio * (height - top - bottom)
    const label = maxValue - ratio * valueRange
    return `<line x1="${left}" y1="${gy.toFixed(1)}" x2="${width - right}" y2="${gy.toFixed(1)}" stroke="currentColor" stroke-opacity="0.10" stroke-width="1"/><text x="${left - 8}" y="${(gy + 4).toFixed(1)}" text-anchor="end" fill="currentColor" fill-opacity="0.55" font-size="${props.compact ? 15 : 18}">${formatAxis(label)}</text>`
  }).join('')

  const lines = validSeries.value.map((series) => {
    const style = palette[series.source] || { color: '#18AFC4' }
    const points = series.points.map((point) => `${x(new Date(point.time).getTime()).toFixed(1)},${y(displayPrice(point.price_cny)).toFixed(1)}`).join(' ')
    const last = series.points[series.points.length - 1]
    const lastX = x(new Date(last.time).getTime()).toFixed(1)
    const lastY = y(displayPrice(last.price_cny)).toFixed(1)
    return `<polyline points="${points}" fill="none" stroke="${style.color}" stroke-width="${props.compact ? 1.6 : 2}" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/><circle cx="${lastX}" cy="${lastY}" r="${props.compact ? 2.4 : 3}" fill="${style.color}" stroke="var(--card)" stroke-width="1.5"/>`
  }).join('')

  const startLabel = formatTimeLabel(minTime, timeRange)
  const endLabel = formatTimeLabel(maxTime, timeRange)
  return `<svg viewBox="0 0 ${width} ${height}" width="100%" height="100%" preserveAspectRatio="none" role="img"><g color="var(--text-sub)">${grid}</g>${lines}<text x="${left}" y="${height - 5}" fill="var(--text-sub)" font-size="${props.compact ? 14 : 18}">${startLabel}</text><text x="${width - right}" y="${height - 5}" text-anchor="end" fill="var(--text-sub)" font-size="${props.compact ? 14 : 18}">${endLabel}</text></svg>`
})
</script>

<style lang="scss" scoped>
.market-chart { width: 100%; min-height: 340rpx; }
.market-chart.compact { min-height: 176rpx; }
.svg-box { width: 100%; height: 340rpx; overflow: hidden; color: var(--text-sub); }
.svg-box.compact { height: 176rpx; }
.chart-empty { min-height: 340rpx; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 24rpx; text-align: center; }
.empty-title { color: var(--text); font-size: 28rpx; font-weight: 600; }
.empty-copy { color: var(--text-sub); font-size: 22rpx; margin-top: 10rpx; }
</style>
