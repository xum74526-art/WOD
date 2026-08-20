<template>
  <view class="market-sparkline" aria-hidden="true" v-html="svgString"></view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { MarketCandle } from '@/api/market'

const props = defineProps<{ candles: MarketCandle[] }>()
const gradientId = `market-spark-${Math.random().toString(36).slice(2, 9)}`

const svgString = computed(() => {
  const values = props.candles
    .map((item) => Number(item.close_price_cny))
    .filter((value) => Number.isFinite(value) && value > 0)
  if (!values.length) return ''

  const width = 320
  const height = 64
  const xPadding = 5
  const yPadding = 8
  const rawMin = Math.min(...values)
  const rawMax = Math.max(...values)
  const padding = Math.max((rawMax - rawMin) * 0.12, rawMax * 0.002, 0.001)
  const min = rawMin - padding
  const max = rawMax + padding
  const range = Math.max(max - min, 0.000001)
  const step = (width - xPadding * 2) / Math.max(values.length - 1, 1)
  const points = values.map((value, index) => ({
    x: xPadding + index * step,
    y: yPadding + (1 - (value - min) / range) * (height - yPadding * 2),
  }))
  const line = points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ')
  const last = points[points.length - 1]!
  const area = `${xPadding},${height - yPadding} ${line} ${last.x.toFixed(1)},${height - yPadding}`

  return `<svg viewBox="0 0 ${width} ${height}" width="100%" height="100%" preserveAspectRatio="none"><defs><linearGradient id="${gradientId}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="var(--primary)" stop-opacity="0.22"/><stop offset="100%" stop-color="var(--primary)" stop-opacity="0"/></linearGradient></defs><polygon points="${area}" fill="url(#${gradientId})"/><polyline points="${line}" fill="none" stroke="var(--primary)" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/><circle cx="${last.x.toFixed(1)}" cy="${last.y.toFixed(1)}" r="3.2" fill="var(--card)" stroke="var(--primary)" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`
})
</script>

<style lang="scss" scoped>
.market-sparkline { width: 100%; height: 64rpx; overflow: hidden; color: var(--primary); }
</style>
