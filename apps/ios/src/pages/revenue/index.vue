<template>
  <view class="page">
    <AppNavBar :title="t('auditedEarningsTitle')" />
    <scroll-view scroll-y class="body">
      <view v-if="summary?.historical_test_total" class="service-warning">
        {{ t('historicalEarningsAuditNotice', { amount: fmtCardHours(summary.historical_test_total) }) }}
      </view>
      <view class="card summary">
        <view class="sum-top">
          <text class="sum-label">{{ t('todayRealizedEarnings') }}</text>
          <AmountText :value="summary?.today ?? 0" prefix="cardHour" size="xl" :trend="amountTrend(summary?.today)" />
        </view>
        <view class="sum-grid">
          <view class="sg-item">
            <text class="sg-label">{{ t('totalRealizedEarnings') }}</text>
            <AmountText :value="summary?.total ?? 0" prefix="cardHour" size="md" :trend="amountTrend(summary?.total)" />
          </view>
          <view class="sg-item">
            <text class="sg-label">{{ t('pendingUsageRebate') }}</text>
            <AmountText :value="summary?.pending_rebate ?? 0" prefix="cardHour" size="md" />
          </view>
          <view class="sg-item">
            <text class="sg-label">{{ t('holdingUnrealizedPnl') }}</text>
            <AmountText :value="summary?.holding_unrealized_pnl ?? 0" prefix="cardHour" size="md" :trend="amountTrend(summary?.holding_unrealized_pnl)" />
          </view>
          <view class="sg-item">
            <text class="sg-label">{{ t('holdingRealizedPnl') }}</text>
            <AmountText :value="summary?.holding_realized_pnl ?? 0" prefix="cardHour" size="md" :trend="amountTrend(summary?.holding_realized_pnl)" />
          </view>
        </view>
        <text class="summary-note">{{ t('auditedEarningsScope') }}</text>
      </view>

      <view class="seg-wrap">
        <SegmentedControl v-model="rangeIndex" :items="rangeLabels" />
      </view>

      <SectionHeader :title="t('auditedEarningsTrend')" />
      <view class="card chart-card">
        <Chart :points="chart" value-key="amount" :height="180" />
      </view>

      <SectionHeader :title="t('auditedEarningsRecords')" />
      <view class="card list-card" v-if="records.length">
        <view v-for="(r, i) in records" :key="r.record_key || `${r.source_type}:${r.id}`" class="rec" :class="{ last: i === records.length - 1 }">
          <view class="rec-left">
            <text class="rec-date">{{ formatDate(r.date || r.created_at) }}</text>
            <text class="rec-sub">{{ recordLabel(r) }}{{ r.asset_id ? ` · #${r.asset_id}` : '' }}</text>
          </view>
          <AmountText :value="r.amount" prefix="cardHour" size="sm" :trend="amountTrend(r.amount)" />
        </view>
      </view>
      <EmptyState v-else :text="t('noAuditedEarningsRecords')">
        <AppIcon name="revenue" :size="56" />
      </EmptyState>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getRevenueSummary, getRevenueChart, getRevenueRecords, type RevenueSummary, type RevenuePoint, type RevenueRecord } from '@/api/revenue'
import { formatDate, fmtCardHours } from '@/utils/format'
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
const rangeLabels = computed(() => [t('sevenDays'), t('thirtyDays'), t('ninetyDays')])

function amountTrend(value: number | null | undefined): 'up' | 'down' | 'none' {
  const amount = Number(value || 0)
  return amount > 0 ? 'up' : amount < 0 ? 'down' : 'none'
}

function recordLabel(record: RevenueRecord): string {
  return t(record.source_type === 'holding_sale' ? 'holdingSalePnlRecord' : 'usageRebateSettledRecord')
}

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
.sum-grid { flex-wrap: wrap; }
.sg-item { width: calc(50% - 12rpx); box-sizing: border-box; background: var(--bg-2); border-radius: var(--radius); padding: 24rpx 28rpx; }
.sg-label { display: block; color: var(--text-sub); font-size: 24rpx; margin-bottom: 12rpx; }
.sg-val { color: var(--text); font-size: 36rpx; font-weight: 700; font-variant-numeric: tabular-nums; }
.summary-note { display: block; margin-top: 24rpx; color: var(--text-sub); font-size: 22rpx; line-height: 1.6; }

.seg-wrap { margin: 32rpx 0 8rpx; }
.chart-card { padding: 24rpx 16rpx; }

.list-card { padding: 4rpx 32rpx; }
.rec { display: flex; justify-content: space-between; align-items: center; padding: 28rpx 0; border-bottom: 1rpx solid var(--divider); }
.rec.last { border-bottom: none; }
.rec-left { display: flex; flex-direction: column; gap: 6rpx; }
.rec-date { color: var(--text); font-size: 28rpx; }
.rec-sub { color: var(--text-dim); font-size: 22rpx; }
</style>
