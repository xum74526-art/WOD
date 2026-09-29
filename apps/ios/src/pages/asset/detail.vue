<template>
  <view class="page">
    <AppNavBar :title="t('k_f508a46b')" />
    <scroll-view scroll-y class="body">
      <view v-if="assetLoading" class="state">{{ t('loading') }}</view>
      <view v-else-if="assetMissing" class="state">
        <EmptyState :text="t('assetNotFound')">
          <AppIcon name="gpu" :size="56" />
        </EmptyState>
      </view>
      <view v-else-if="assetLoadFailed || !asset" class="state">
        <EmptyState :text="t('assetLoadFailedDesc')">
          <AppIcon name="gpu" :size="56" />
        </EmptyState>
      </view>
      <template v-else>
        <view v-if="asset.purchase_type === 'usage' && asset.audited_earnings_enabled === false" class="service-warning">{{ t('revenueSettlementUnavailable') }}</view>
        <view v-if="asset.reward_service_enabled === false && asset.historical_test_reward" class="service-warning">{{ t('rewardServiceUnavailable') }}</view>
        <view class="card hero">
          <view class="hero-top">
            <view class="hero-name-wrap">
              <text class="hero-name">{{ localizeProductName(asset.product_name || t('算力资产'), i18n.lang) }}</text>
              <text class="hero-gpu">{{ asset.gpu_model || '-' }} × {{ asset.quantity }}</text>
            </view>
            <StatusBadge :text="badge.text" :type="badge.type" />
          </view>
          <view class="hero-value">
            <text class="hero-label">{{ t(asset.purchase_type === 'holding' ? 'purchaseCost' : '当前价值') }}</text>
            <AmountText :value="asset.value" currency="ledger" size="lg" />
          </view>
          <!-- 持有模式：显示当前市场价 + 盈亏 -->
          <view v-if="asset.purchase_type === 'holding' && asset.current_price != null" class="sell-info">
            <view class="si-row">
              <text class="si-label">{{ t('k_87165f6a') }}</text>
              <text class="si-val" :class="{ up: (asset.pnl ?? 0) >= 0, down: (asset.pnl ?? 0) < 0 }">{{ formatCardHourCurrency(asset.current_price) }}</text>
            </view>
            <view class="si-row">
              <text class="si-label">{{ t('k_a8401d10') }}</text>
              <text class="si-val" :class="{ up: (asset.pnl ?? 0) >= 0, down: (asset.pnl ?? 0) < 0 }">
                {{ (asset.pnl ?? 0) >= 0 ? '+' : '' }}{{ formatCardHourCurrency(asset.pnl) }} ({{ (asset.pnl_pct ?? 0) >= 0 ? '+' : '' }}{{ formatNumber(asset.pnl_pct ?? 0) }}%)
              </text>
            </view>
          </view>
          <view v-else-if="asset.purchase_type === 'usage' && asset.audited_earnings_enabled" class="hero-grid">
            <view class="hg-item">
              <text class="hg-label">{{ t('pendingUsageRebate') }}</text>
              <AmountText :value="asset.pending_rebate ?? 0" currency="ledger" size="md" />
            </view>
            <view class="hg-item">
              <text class="hg-label">{{ t('rebated') }}</text>
              <AmountText :value="asset.settled_rebate ?? 0" currency="ledger" size="md" trend="up" />
            </view>
          </view>
        </view>

        <view v-if="asset.purchase_type === 'holding' && !asset.can_sell && asset.trading_unavailable_reason" class="service-warning">{{ tr(asset.trading_unavailable_reason) }}</view>
        <SectionHeader v-if="asset.purchase_type === 'usage' && asset.audited_earnings_enabled" :title="t('accountRevenueLast7Days')" />
        <view v-if="asset.purchase_type === 'usage' && asset.audited_earnings_enabled" class="card chart-card">
          <view v-if="accountRevenueChartLoading" class="chart-state">{{ t('loading') }}</view>
          <view v-else-if="accountRevenueChartFailed" class="chart-state unavailable">{{ t('accountRevenueChartUnavailable') }}</view>
          <Chart v-else :points="accountRevenueChart" value-key="amount" :height="180" />
        </view>

        <SectionHeader :title="t('k_81aedca2')" />
        <view class="card info-card">
          <view class="row"><text class="sk">{{ t('k_21c8bb00') }}</text><text class="sv">{{ t(asset.purchase_type === 'holding' ? 'holdingMode' : 'usageMode') }}</text></view>
          <view class="row"><text class="sk">{{ t('k_b44c0f33') }}</text><text class="sv">{{ formatDate(asset.start_at) || '-' }}</text></view>
          <view class="row" v-if="asset.purchase_type === 'usage'"><text class="sk">{{ t('k_eccb8cdc') }}</text><text class="sv">{{ formatDate(asset.end_at) || '-' }}</text></view>
          <view class="row" v-if="asset.purchase_type === 'usage'"><text class="sk">{{ t('k_927babb3') }}</text><text class="sv">{{ t('{days} 天', { days: asset.remaining_days ?? 0 }) }}</text></view>
          <view class="row" v-if="asset.pending_rebate">
            <text class="sk">{{ t('k_64913945') }}</text>
            <text class="sv up">+{{ formatCardHourCurrency(asset.pending_rebate) }}</text>
          </view>
          <view class="row" v-if="asset.settled_rebate">
            <text class="sk">{{ t('k_ca7204ca') }}</text>
            <text class="sv up">+{{ formatCardHourCurrency(asset.settled_rebate) }}</text>
          </view>
          <view class="row" v-if="asset.rebate_status === 'forfeited'">
            <text class="sk">{{ t('k_080a8165') }}</text>
            <text class="sv dim">{{ t('k_13d3d059') }}</text>
          </view>
        </view>

        <SectionHeader v-if="asset.order_id" :title="t('k_f654f668')" />
        <view v-if="asset.order_id" class="card link-card" @tap="goOrder">
          <view class="lc-left">
            <text class="lc-label">{{ t('k_1e8dc255') }}</text>
            <text class="lc-no">#{{ asset.order_id }}</text>
          </view>
          <AppIcon name="chevron" :size="36" />
        </view>
      </template>
    </scroll-view>
    <BottomActionBar v-if="asset">
      <DirectTradeAssetActions v-if="commerce.directTradeEnabled" :asset="asset" />
      <view v-else-if="commerce.matchmakingEnabled && (asset.can_sell || asset.purchase_type === 'usage')" class="primary-btn" @tap="submitRenewalRequirement">{{ t('submitRequirement') }}</view>
      <view v-else-if="!commerce.available" class="primary-btn disabled">{{ t('dataUnavailable') }}</view>
      <view v-else class="primary-btn disabled">{{ t('holdingTradingUnavailable') }}</view>
    </BottomActionBar>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getAsset, type AssetItem } from '@/api/asset'
import { ApiRequestError } from '@/api/request'
import { getRevenueChart, type RevenuePoint } from '@/api/revenue'
import { formatNumber, formatCardHourCurrency, formatDate } from '@/utils/format'
import AppNavBar from '@/components/AppNavBar.vue'
import AmountText from '@/components/AmountText.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import Chart from '@/components/Chart.vue'
import BottomActionBar from '@/components/BottomActionBar.vue'
import EmptyState from '@/components/EmptyState.vue'
import AppIcon from '@/components/AppIcon.vue'
import DirectTradeAssetActions from '@/components/direct-trade/DirectTradeAssetActions.vue'
import { navigateTo as nav } from '@/utils/nav'
import { useI18nStore } from '@/store/i18n'
import { useCommerceStore } from '@/store/commerce'
import { localizeProductName } from '@/utils/localize-content'
import { saveInquiryRequestPrefill } from '@/utils/inquiry-request'
import { ACCOUNT_REVENUE_RANGE_DAYS, startAssetDetailRequests } from '@/utils/asset-detail-requests'

const i18n = useI18nStore()
const { t, tr } = i18n
const commerce = useCommerceStore()
const asset = ref<AssetItem | null>(null)
const assetLoading = ref(true)
const assetMissing = ref(false)
const assetLoadFailed = ref(false)
const accountRevenueChart = ref<RevenuePoint[]>([])
const accountRevenueChartLoading = ref(false)
const accountRevenueChartFailed = ref(false)

onLoad(async (opts) => {
  const id = Number(opts?.id || 0)
  if (!id) {
    assetMissing.value = true
    assetLoading.value = false
    return
  }

  accountRevenueChartLoading.value = true
  const requests = startAssetDetailRequests(
    getAsset(id),
    getRevenueChart(ACCOUNT_REVENUE_RANGE_DAYS, { silent: true }),
  )

  void requests.accountRevenueChart.then((result) => {
    if (result.status === 'fulfilled') {
      accountRevenueChart.value = result.value
    } else {
      accountRevenueChartFailed.value = true
    }
    accountRevenueChartLoading.value = false
  })

  const assetResult = await requests.asset
  if (assetResult.status === 'fulfilled') {
    asset.value = assetResult.value
  } else if (assetResult.reason instanceof ApiRequestError && assetResult.reason.statusCode === 404) {
    assetMissing.value = true
  } else {
    assetLoadFailed.value = true
  }
  assetLoading.value = false
})

const badge = computed(() => {
  const current = asset.value
  const s = asset.value?.status
  if (s === 'active' || s === 'running') {
    return { text: t(current?.purchase_type === 'holding' ? 'holding' : 'running'), type: 'running' as const }
  }
  if (s === 'expired') return { text: t('expired'), type: 'expired' as const }
  if (s === 'sold') return { text: t('sold'), type: 'done' as const }
  if (s === 'used') return { text: t('使用中'), type: 'running' as const }
  if (s === 'done') return { text: t('completed'), type: 'done' as const }
  if (s === 'canceled') return { text: t('canceled'), type: 'canceled' as const }
  return { text: t('statusPending'), type: 'default' as const }
})

function goOrder() {
  const oid = asset.value?.order_id
  if (!oid) return
  nav(`/pages/order/detail?id=${oid}`)
}

function submitRenewalRequirement() {
  const current = asset.value
  if (!current?.product_id) return
  saveInquiryRequestPrefill({
    product_id: current.product_id,
    source: 'existing_asset',
    gpu_model: current.gpu_model || current.product_name || 'GPU',
    quantity: Math.max(1, Number(current.quantity) || 1),
    gpu_hours: 24,
    product_name: current.product_name || undefined,
  })
  nav('/pages/buy-request/index?compose=1')
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.body { flex: 1; padding: 0 32rpx 200rpx; }
.state { color: var(--text-sub); text-align: center; padding: 120rpx 0; font-size: 28rpx; }
.card { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }
.service-warning { color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); padding: 24rpx; margin-bottom: 20rpx; font-size: 24rpx; line-height: 1.6; }

.hero { padding: 36rpx 32rpx; }
.hero-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 16rpx; }
.hero-name-wrap { flex: 1; min-width: 0; }
.hero-name { color: var(--text); font-size: 40rpx; font-weight: 700; display: block; }
.hero-gpu { color: var(--text-sub); font-size: 26rpx; margin-top: 8rpx; display: block; }
.hero-value { display: flex; align-items: baseline; gap: 20rpx; margin-top: 32rpx; }
.hero-label { color: var(--text-sub); font-size: 26rpx; }
.hero-grid { display: flex; gap: 24rpx; margin-top: 32rpx; }
.hg-item { flex: 1; background: var(--bg-2); border-radius: var(--radius); padding: 24rpx 28rpx; }
.hg-label { display: block; color: var(--text-sub); font-size: 24rpx; margin-bottom: 12rpx; }

.chart-card { padding: 24rpx 16rpx; }
.chart-state { min-height: 180rpx; display: flex; align-items: center; justify-content: center; padding: 24rpx; color: var(--text-sub); text-align: center; font-size: 26rpx; line-height: 1.6; }
.chart-state.unavailable { color: var(--text-dim); }
.info-card { padding: 4rpx 32rpx; }
.row { display: flex; justify-content: space-between; align-items: center; padding: 28rpx 0; border-bottom: 1rpx solid var(--divider); }
.row:last-child { border-bottom: none; }
.sk { color: var(--text-sub); font-size: 28rpx; }
.sv { color: var(--text); font-size: 28rpx; font-variant-numeric: tabular-nums; }
.sv.up { color: var(--up); font-weight: 700; }
.sv.dim { color: var(--text-dim); }

.link-card { display: flex; align-items: center; justify-content: space-between; padding: 28rpx 32rpx; color: var(--text-sub); }
.lc-left { display: flex; flex-direction: column; gap: 8rpx; }
.lc-label { color: var(--text-sub); font-size: 24rpx; }
.lc-no { color: var(--text); font-size: 30rpx; font-weight: 600; font-variant-numeric: tabular-nums; }

.primary-btn { background: var(--primary); color: #fff; text-align: center; padding: 28rpx 0; border-radius: var(--radius); font-size: 32rpx; font-weight: 600; }
.primary-btn.disabled { opacity: 0.45; }
</style>
