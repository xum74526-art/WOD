<template>
  <view class="page">
    <AppNavBar :title="t('k_9a3c9be5')" />
    <scroll-view scroll-y class="body">
      <view v-if="summary?.revenue_settlement_enabled === false" class="service-warning">
        {{ t('revenueSettlementUnavailable') }}
        <text v-if="summary.historical_test_total">{{ t('historicalRevenueExcluded', { amount: fmtCH(summary.historical_test_total) }) }}</text>
      </view>
      <view class="card summary">
        <view class="sum-top">
          <text class="sum-label">{{ t('todayRevenue') }}</text>
          <AmountText :value="toCardHours(summary?.today ?? 0)" prefix="卡时" size="xl" trend="up" />
        </view>
        <view class="sum-grid">
          <view class="sg-item">
            <text class="sg-label">{{ t('cumulativeRevenue') }}</text>
            <AmountText :value="toCardHours(summary?.total ?? 0)" prefix="卡时" size="md" trend="up" />
          </view>
          <view class="sg-item">
            <text class="sg-label">{{ t('k_a20449e5') }}</text>
            <text class="sg-val">{{ ratePct }}%</text>
          </view>
        </view>
      </view>

      <view class="seg-wrap">
        <SegmentedControl v-model="rangeIndex" :items="['7天', '30天', '90天']" />
      </view>

      <SectionHeader :title="t('k_86296786')" />
      <view class="card chart-card">
        <Chart :points="chart" value-key="amount" :height="180" />
      </view>

      <SectionHeader :title="t('k_764d7c0c')" />
      <view class="card list-card" v-if="records.length">
        <view v-for="(r, i) in records" :key="r.id" class="rec" :class="{ last: i === records.length - 1 }">
          <view class="rec-left">
            <text class="rec-date">{{ formatDate(r.date || r.created_at) }}</text>
            <text class="rec-sub">{{ t('k_6fff6f74') }}</text>
          </view>
          <AmountText :value="toCardHours(r.amount)" prefix="+卡时" size="sm" trend="up" />
        </view>
      </view>
      <EmptyState v-else text="暂无收益记录">
        <AppIcon name="revenue" :size="56" />
      </EmptyState>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getRevenueSummary, getRevenueChart, getRevenueRecords, type RevenueSummary, type RevenuePoint, type RevenueRecord } from '@/api/revenue'
import { fmtCH, formatDate, formatNumber, toCardHours } from '@/utils/format'
import AppNavBar from '@/components/AppNavBar.vue'
import AmountText from '@/components/AmountText.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import Chart from '@/components/Chart.vue'
import EmptyState from '@/components/EmptyState.vue'
import AppIcon from '@/components/AppIcon.vue'
import { useI18nStore } from '@/store/i18n'

const { t } = useI18nStore()
const RANGES = [7, 30, 90] as const
const rangeIndex = ref(1)
const summary = ref<RevenueSummary | null>(null)
const chart = ref<RevenuePoint[]>([])
const records = ref<RevenueRecord[]>([])

const range = computed(() => RANGES[rangeIndex.value])
const ratePct = computed(() => formatNumber(Number(summary.value?.rate) || 0))

async function fetchChart() {
  try {
    chart.value = await getRevenueChart(range.value)
  } catch {
    /* request 已 toast */
  }
}

onLoad(async () => {
  try {
    const [s, c, rs] = await Promise.all([getRevenueSummary(), getRevenueChart(range.value), getRevenueRecords()])
    summary.value = s
    chart.value = c
    records.value = rs
  } catch {
    /* request 已 toast */
  }
})

watch(rangeIndex, () => fetchChart())
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.body { flex: 1; padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.card { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }
.service-warning { color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); padding: 24rpx; margin-bottom: 20rpx; font-size: 24rpx; line-height: 1.6; }
.service-warning text { display: block; margin-top: 6rpx; }

.summary { padding: 40rpx 32rpx; }
.sum-top { display: flex; flex-direction: column; gap: 12rpx; }
.sum-label { color: var(--text-sub); font-size: 26rpx; }
.sum-grid { display: flex; gap: 24rpx; margin-top: 32rpx; }
.sg-item { flex: 1; background: var(--bg-2); border-radius: var(--radius); padding: 24rpx 28rpx; }
.sg-label { display: block; color: var(--text-sub); font-size: 24rpx; margin-bottom: 12rpx; }
.sg-val { color: var(--text); font-size: 36rpx; font-weight: 700; font-variant-numeric: tabular-nums; }

.seg-wrap { margin: 32rpx 0 8rpx; }
.chart-card { padding: 24rpx 16rpx; }

.list-card { padding: 4rpx 32rpx; }
.rec { display: flex; justify-content: space-between; align-items: center; padding: 28rpx 0; border-bottom: 1rpx solid var(--divider); }
.rec.last { border-bottom: none; }
.rec-left { display: flex; flex-direction: column; gap: 6rpx; }
.rec-date { color: var(--text); font-size: 28rpx; }
.rec-sub { color: var(--text-dim); font-size: 22rpx; }
</style>
