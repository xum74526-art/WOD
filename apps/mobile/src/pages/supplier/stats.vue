<template>
  <view class="page">
    <AppNavBar :title="t('k_fa43d375')" />
    <view class="shell">
      <view v-if="loadError" class="load-error">
        <text>{{ t('supplierLoadFailedDesc') }}</text>
        <text class="load-retry" @tap="load">{{ t('retry') }}</text>
      </view>
      <view class="card stats-card">
        <view class="stat-row">
          <view class="stat"><text class="sl">{{ t('k_c615660d') }}</text><text class="sv">{{ stats?.total_products ?? 0 }}</text></view>
          <view class="stat"><text class="sl">{{ t('k_c619ecd5') }}</text><text class="sv">{{ stats?.total_orders ?? 0 }}</text></view>
        </view>
      </view>

      <SectionHeader :title="t('k_fdb8a664')" />
      <view class="card chart-card" v-if="stats?.revenue_trend?.length">
        <Chart :points="stats.revenue_trend" value-key="amount" :height="160" />
      </view>
      <view v-else class="card ph">{{ t('k_21efd88b') }}</view>

      <SectionHeader :title="t('k_f02865ff')" />
      <view v-if="!stats?.device_stats?.length" class="card ph">{{ t('k_bcc241e0') }}</view>
      <view v-for="d in stats?.device_stats" :key="d.name" class="card urow">
        <view class="ul">
          <text class="un">{{ localizeProductName(d.name, i18n.lang) }}</text>
          <text class="ug">{{ d.gpu_model }} · {{ t('{count} 个订单', { count: d.order_count }) }} · {{ fmtCH(d.price) }}/h</text>
        </view>
        <view class="ur">
          <view class="bar-bg"><view class="bar-fill" :style="{ width: utilizationWidth(d.utilization) }"></view></view>
          <text class="uv">{{ formatNumber(d.utilization) }}%</text>
        </view>
      </view>

      <SectionHeader :title="t('k_9d89260e')" />
      <view class="card alert-card">
        <view v-if="stats?.attention_count" class="alert-item">
          <view class="alert-dot danger"></view>
          <text class="alert-text">{{ t('devicesNeedAttentionCount', { count: stats.attention_count }) }}</text>
        </view>
        <view v-else-if="stats?.total_products" class="alert-item">
          <view class="alert-dot ok"></view>
          <text class="alert-text">{{ t('noDeviceAlertsDetected') }}</text>
        </view>
        <view v-else class="alert-item">
          <view class="alert-dot neutral"></view>
          <text class="alert-text">{{ t('noDevicesToAssess') }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { request } from '@/api/request'
import { getSupplierDevices } from '@/api/supplier'
import AppNavBar from '@/components/AppNavBar.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import Chart from '@/components/Chart.vue'
import EmptyState from '@/components/EmptyState.vue'
import { fmtCH, formatNumber } from '@/utils/format'
import { useI18nStore } from '@/store/i18n'
import { localizeProductName } from '@/utils/localize-content'

const i18n = useI18nStore()
const { t } = i18n
const stats = ref<{ device_stats: any[]; revenue_trend: any[]; total_products: number; total_orders: number; attention_count: number } | null>(null)
const loadError = ref(false)

function utilizationWidth(value: unknown): string {
  const numericValue = Number(value)
  const clamped = Number.isFinite(numericValue) ? Math.min(100, Math.max(0, numericValue)) : 0
  return `${clamped}%`
}

async function load() {
  loadError.value = false
  try {
    const [analytics, devices] = await Promise.all([
      request<any>({ url: '/supplier/analytics' }),
      getSupplierDevices('all'),
    ])
    stats.value = {
      total_products: devices.length,
      total_orders: Number(analytics.metrics?.order_count || 0),
      revenue_trend: analytics.series || [],
      device_stats: devices.map(device => ({
        ...device,
        utilization: Number(analytics.metrics?.utilization_rate || 0),
      })),
      attention_count: devices.filter(device => device.status !== 'online').length,
    }
  } catch {
    stats.value = null
    loadError.value = true
  }
}
onShow(() => load())
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--card-border); }
.stats-card { padding: 32rpx; margin: 24rpx 0; }
.stat-row { display: flex; justify-content: space-around; }
.stat { text-align: center; }
.sl { color: var(--text-sub); font-size: 24rpx; display: block; }
.sv { color: var(--text); font-size: 44rpx; font-weight: 800; display: block; margin-top: 8rpx; font-variant-numeric: tabular-nums; }
.chart-card { padding: 24rpx 16rpx; margin-bottom: 24rpx; }
.ph { padding: 40rpx; text-align: center; color: var(--text-sub); font-size: 26rpx; }
.urow { display: flex; justify-content: space-between; align-items: center; padding: 28rpx 32rpx; margin-bottom: 16rpx; }
.un { color: var(--text); font-size: 28rpx; font-weight: 600; display: block; }
.ug { color: var(--text-sub); font-size: 22rpx; margin-top: 6rpx; display: block; }
.ur { display: flex; align-items: center; gap: 12rpx; }
.bar-bg { width: 120rpx; height: 12rpx; background: var(--divider); border-radius: 6rpx; overflow: hidden; }
.bar-fill { height: 100%; background: var(--primary); border-radius: 6rpx; }
.uv { color: var(--text); font-size: 24rpx; font-weight: 600; min-width: 60rpx; text-align: right; }
.alert-card { padding: 24rpx 32rpx; }
.alert-item { display: flex; align-items: center; gap: 16rpx; }
.alert-dot { width: 16rpx; height: 16rpx; border-radius: 8rpx; }
.alert-dot.ok { background: var(--up); }
.alert-dot.danger { background: var(--down); }
.alert-dot.neutral { background: var(--text-dim); }
.alert-text { color: var(--text-sub); font-size: 26rpx; }
.load-error { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; padding: 20rpx 24rpx; margin: 24rpx 0 0; color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); font-size: 23rpx; line-height: 1.5; }
.load-retry { flex-shrink: 0; color: var(--primary); font-weight: 700; min-height: 64rpx; display: flex; align-items: center; }
</style>
