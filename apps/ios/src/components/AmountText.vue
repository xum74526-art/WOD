<template>
  <text class="amount" :class="[sizeClass, trendClass]">
    <text class="prefix" v-if="resolvedPrefix">{{ resolvedPrefix }}</text>
    <text class="int">{{ intPart }}</text>
    <text class="dec" v-if="decPart">.{{ decPart }}</text>
  </text>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18nStore } from '@/store/i18n'
import { cardHoursToDisplayCurrency, cnyToDisplayCurrency, displayCurrencySymbol, formatNumber } from '@/utils/format'

const i18n = useI18nStore()
const { t } = i18n
const props = withDefaults(defineProps<{
  value: number | string
  prefix?: string
  currency?: 'plain' | 'ledger' | 'cny' | 'settlement'
  size?: 'sm' | 'md' | 'lg' | 'xl'
  trend?: 'up' | 'down' | 'none'
}>(), {
  prefix: '',
  currency: 'plain',
  size: 'md',
  trend: 'none',
})

const str = computed(() => {
  const value = props.currency === 'ledger'
    ? cardHoursToDisplayCurrency(props.value)
    : props.currency === 'cny'
      ? cnyToDisplayCurrency(props.value)
      : props.value
  return formatNumber(value, {
    locale: i18n.locale,
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  })
})
const resolvedPrefix = computed(() => props.currency === 'plain' ? t(props.prefix) : props.currency === 'settlement' ? '¥' : displayCurrencySymbol())
const parts = computed(() => str.value.split('.'))
const intPart = computed(() => parts.value[0])
const decPart = computed(() => parts.value[1])
const sizeClass = computed(() => `size-${props.size}`)
const trendClass = computed(() => (props.trend !== 'none' ? `trend-${props.trend}` : ''))
</script>

<style lang="scss" scoped>
.amount { font-variant-numeric: tabular-nums; font-weight: 800; display: inline-flex; align-items: baseline; color: var(--text); }
.prefix { font-size: 0.55em; margin-right: 4rpx; font-weight: 500; color: var(--text-sub); }
.dec { font-size: 0.55em; color: var(--text-sub); }
.size-sm { font-size: 28rpx; }
.size-md { font-size: 40rpx; }
.size-lg { font-size: 56rpx; }
.size-xl { font-size: 76rpx; }
.trend-up { color: var(--up); }
.trend-down { color: var(--down); }
</style>
