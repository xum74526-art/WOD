<template>
  <view class="chart-wrap">
    <view v-if="!points.length" class="empty">{{ t('noData') }}</view>
    <view v-else class="svg-box" v-html="svgString"></view>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18nStore } from '@/store/i18n'

const { t } = useI18nStore()

const props = withDefaults(defineProps<{
  points: any[]
  valueKey?: string
  color?: string
  height?: number
}>(), { valueKey: 'amount', color: '', height: 160 })

const svgString = computed(() => {
  const pts = props.points
  if (!pts.length) return ''
  const c = props.color || 'var(--primary)'
  const W = 320, H = 160, PAD = 16
  const vals = pts.map((p) => Number(p[props.valueKey]) || 0)
  const max = Math.max(...vals, 0.001)
  const min = Math.min(...vals, 0)
  const range = max - min || 1
  const stepX = (W - PAD * 2) / (pts.length - 1 || 1)
  const coords = pts.map((p, i) => {
    const x = PAD + i * stepX
    const y = H - PAD - (((Number(p[props.valueKey]) || 0) - min) / range) * (H - PAD * 2)
    return [x, y] as [number, number]
  })
  const line = coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const last = coords[coords.length - 1]
  const area = `${PAD},${H - PAD} ${line} ${last[0].toFixed(1)},${H - PAD}`
  const gid = 'cg' + Math.random().toString(36).slice(2, 7)
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${props.height}" preserveAspectRatio="none"><defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${c}" stop-opacity="0.25"/><stop offset="100%" stop-color="${c}" stop-opacity="0"/></linearGradient></defs><polygon points="${area}" fill="url(#${gid})"/><polyline points="${line}" fill="none" stroke="${c}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/></svg>`
})
</script>

<style lang="scss" scoped>
.chart-wrap { width: 100%; }
.svg-box { width: 100%; }
.empty { color: var(--text-sub); text-align: center; padding: 60rpx 0; font-size: 26rpx; }
</style>
