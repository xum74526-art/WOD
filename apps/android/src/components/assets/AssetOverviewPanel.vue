<template>
  <view class="asset-panel">
    <view v-if="loading && !hasData" class="asset-panel__skeleton" aria-hidden="true">
      <view class="asset-panel__skeleton-block" style="height: 310rpx"></view>
      <view v-for="n in 3" :key="n" class="asset-panel__skeleton-block"></view>
    </view>

    <view v-else-if="error && !hasData" class="asset-panel__state">
      <view class="asset-panel__state-icon"><AppIcon name="wallet" :size="54" /></view>
      <text class="asset-panel__state-title">{{ t('dataUnavailable') }}</text>
      <text class="asset-panel__state-text">{{ t('assetLoadFailedDesc') }}</text>
      <view class="asset-panel__state-action" @tap="$emit('retry')">{{ t('retry') }}</view>
    </view>

    <template v-else>
      <view class="asset-panel__hero">
        <text class="asset-panel__eyebrow">{{ t('assetTotalValue') }}</text>
        <view class="asset-panel__amount">
          <text class="asset-panel__amount-value">{{ assetAvailable && walletAvailable ? fmtCHn(totalAsset) : '--' }}</text>
          <text class="asset-panel__amount-unit">{{ t('cardHour') }}</text>
        </view>
        <text class="asset-panel__hero-note">{{ updatedLabel }}</text>
        <view class="asset-panel__metrics">
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value">{{ walletAvailable ? fmtCHn(walletBalance) : '--' }}</text>
            <text class="asset-panel__metric-label">{{ t('walletBalance') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value" :class="earningsTone(todayRevenue)">{{ assetAvailable ? `${todayRevenue > 0 ? '+' : ''}${fmtCardHours(todayRevenue)}` : '--' }}</text>
            <text class="asset-panel__metric-label">{{ t('todayRealizedEarnings') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value positive">{{ walletAvailable ? fmtCardHours(totalIncome) : '--' }}</text>
            <text class="asset-panel__metric-label">{{ t('totalRealizedEarnings') }}</text>
          </view>
        </view>
      </view>

      <view class="asset-panel__section">
        <view class="asset-panel__section-head">
          <text class="asset-panel__section-title">{{ t('assetComposition') }}</text>
          <text class="asset-panel__section-meta">{{ t('countResources', { count: activeCount }) }}</text>
        </view>
        <view class="asset-panel__summary">
          <view class="asset-panel__summary-item">
            <text class="asset-panel__summary-label">{{ t('computeAssets') }}</text>
            <text class="asset-panel__summary-value">{{ assetAvailable ? fmtCH(summary?.total_value) : '--' }}</text>
          </view>
          <view class="asset-panel__summary-item">
            <text class="asset-panel__summary-label">{{ t('walletBalance') }}</text>
            <text class="asset-panel__summary-value">{{ walletAvailable ? fmtCH(walletBalance) : '--' }}</text>
          </view>
          <view class="asset-panel__summary-item">
            <text class="asset-panel__summary-label">{{ t('pendingUsageRebate') }}</text>
            <text class="asset-panel__summary-value">{{ assetAvailable ? `${fmtCardHours(summary?.pending_revenue)} ${t('cardHour')}` : '--' }}</text>
          </view>
          <view class="asset-panel__summary-item">
            <text class="asset-panel__summary-label">{{ t('activeResources') }}</text>
            <text class="asset-panel__summary-value">{{ assetAvailable ? activeCount : '--' }}</text>
          </view>
        </view>
      </view>

      <view class="asset-panel__section">
        <view class="asset-panel__section-head">
          <text class="asset-panel__section-title">{{ t('recentAssets') }}</text>
          <text class="asset-panel__section-meta">{{ assets.length ? t('showingLatest', { count: Math.min(assets.length, 3) }) : t('noData') }}</text>
        </view>
        <view v-if="!assetAvailable" class="asset-panel__state">
          <text class="asset-panel__state-title">{{ t('dataUnavailable') }}</text>
          <text class="asset-panel__state-text">{{ t('assetLoadFailedDesc') }}</text>
          <view class="asset-panel__state-action" @tap="$emit('retry')">{{ t('retry') }}</view>
        </view>
        <view v-else-if="assets.length" class="asset-panel__list">
          <view
            v-for="asset in assets.slice(0, 3)"
            :key="asset.id"
            class="asset-panel__row"
            @tap="$emit('navigate', '/pages/asset/detail?id=' + asset.id)"
          >
            <view class="asset-panel__row-icon"><AppIcon name="gpu" :size="34" /></view>
            <view class="asset-panel__row-main">
              <text class="asset-panel__row-title">{{ localizeProductName(asset.product_name, i18n.lang) }}</text>
              <text class="asset-panel__row-meta">{{ asset.gpu_model || t('computeResource') }} · {{ t(asset.purchase_type === 'holding' ? 'holdingMode' : (asset.status === 'active' ? 'running' : 'expired')) }}</text>
            </view>
            <view class="asset-panel__row-side">
              <text class="asset-panel__row-value" :class="asset.purchase_type === 'holding' ? ((asset.pnl ?? 0) >= 0 ? 'positive' : 'danger') : 'positive'">{{ asset.purchase_type === 'holding' ? fmtCH(asset.current_price ?? asset.value) : '+' + fmtCH(asset.today_revenue) }}</text>
              <text class="asset-panel__row-hint">{{ t(asset.purchase_type === 'holding' ? 'currentPrice' : 'today') }}</text>
            </view>
          </view>
        </view>
        <view v-else class="asset-panel__state">
          <view class="asset-panel__state-icon"><AppIcon name="gpu" :size="50" /></view>
          <text class="asset-panel__state-title">{{ t('noComputeAssets') }}</text>
          <text class="asset-panel__state-text">{{ t('noComputeAssetsDesc') }}</text>
        </view>
      </view>

      <view class="asset-panel__actions">
        <view class="asset-panel__button primary" @tap="$emit('navigate', '/pages/wallet/index')">{{ t('viewWallet') }}</view>
        <view class="asset-panel__button secondary" @tap="$emit('navigate', '/pages/wallet/ledger')">{{ t('viewLedger') }}</view>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AssetItem, AssetSummary } from '@/api/asset'
import AppIcon from '@/components/AppIcon.vue'
import { useI18nStore } from '@/store/i18n'
import { fmtCH, fmtCHn, fmtCardHours } from '@/utils/format'
import { localizeProductName } from '@/utils/localize-content'

const props = defineProps<{
  summary: AssetSummary | null
  assets: AssetItem[]
  totalAsset: number
  walletBalance: number
  totalIncome: number
  todayRevenue: number
  activeCount: number
  assetAvailable: boolean
  walletAvailable: boolean
  loading: boolean
  error: boolean
  updatedAt: number
}>()

defineEmits<{
  (event: 'navigate', url: string): void
  (event: 'retry'): void
}>()

const i18n = useI18nStore()
const { t } = i18n
const hasData = computed(() => !!props.summary || props.walletBalance > 0 || props.assets.length > 0)
const updatedLabel = computed(() => props.updatedAt ? t('dataUpdated') : t('waitingForData'))

function earningsTone(value: number): string {
  return value > 0 ? 'positive' : value < 0 ? 'danger' : ''
}
</script>
