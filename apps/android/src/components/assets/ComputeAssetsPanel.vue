<template>
  <view class="asset-panel">
    <view v-if="loading && !summary" class="asset-panel__skeleton" aria-hidden="true">
      <view class="asset-panel__skeleton-block" style="height: 310rpx"></view>
      <view v-for="n in 3" :key="n" class="asset-panel__skeleton-block"></view>
    </view>

    <view v-else-if="error && !summary" class="asset-panel__state">
      <view class="asset-panel__state-icon"><AppIcon name="gpu" :size="54" /></view>
      <text class="asset-panel__state-title">{{ t('dataUnavailable') }}</text>
      <text class="asset-panel__state-text">{{ t('computeLoadFailedDesc') }}</text>
      <view class="asset-panel__state-action" @tap="$emit('retry')">{{ t('retry') }}</view>
    </view>

    <template v-else>
      <view class="asset-panel__hero">
        <text class="asset-panel__eyebrow">{{ t('computeAssetValue') }}</text>
        <view class="asset-panel__amount">
          <text class="asset-panel__amount-value">{{ fmtCardHours(summary?.total_value) }}</text>
          <text class="asset-panel__amount-unit">{{ t('cardHour') }}</text>
        </view>
        <text class="asset-panel__hero-note">{{ t('computeAssetsSummary') }}</text>
        <view class="asset-panel__metrics">
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value">{{ activeCount }}</text>
            <text class="asset-panel__metric-label">{{ t('activeResources') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value" :class="earningsTone(todayRevenue)">{{ todayRevenue > 0 ? '+' : '' }}{{ fmtCardHours(todayRevenue) }}</text>
            <text class="asset-panel__metric-label">{{ t('todayRealizedEarnings') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value" :class="expiringCount ? 'warning' : ''">{{ expiringCount }}</text>
            <text class="asset-panel__metric-label">{{ t('expiringIn7Days') }}</text>
          </view>
        </view>
      </view>

      <view class="asset-panel__section">
        <SegmentedControl :items="tabLabels" :model-value="tab" @update:model-value="$emit('update-tab', $event)" />
      </view>

      <view class="asset-panel__section">
        <view class="asset-panel__section-head">
          <text class="asset-panel__section-title">{{ t('computeResourceList') }}</text>
          <text class="asset-panel__section-meta">{{ t('countItems', { count: items.length }) }}</text>
        </view>

        <view v-if="listLoading" class="asset-panel__skeleton" aria-hidden="true">
          <view v-for="n in 3" :key="n" class="asset-panel__skeleton-block"></view>
        </view>

        <view v-else-if="items.length" class="asset-panel__list">
          <view
            v-for="asset in items"
            :key="asset.id"
            class="asset-panel__row"
            @tap="$emit('navigate', '/pages/asset/detail?id=' + asset.id)"
          >
            <view class="asset-panel__row-icon"><AppIcon name="gpu" :size="34" /></view>
            <view class="asset-panel__row-main">
              <text class="asset-panel__row-title">{{ localizeProductName(asset.product_name, i18n.lang) }}</text>
              <text class="asset-panel__row-meta">
                {{ asset.gpu_model || t('computeResource') }} · {{ remainingText(asset) }}
              </text>
            </view>
            <view class="asset-panel__row-side">
              <text class="asset-panel__row-value" :class="earningsTone(assetEarnings(asset))">{{ signedAssetEarnings(asset) }}</text>
              <text class="asset-panel__row-hint">{{ t(asset.purchase_type === 'holding' ? 'pnl' : 'rebateInfo') }}</text>
            </view>
          </view>
        </view>

        <view v-else class="asset-panel__state">
          <view class="asset-panel__state-icon"><AppIcon name="gpu" :size="50" /></view>
          <text class="asset-panel__state-title">{{ emptyTitle }}</text>
          <text class="asset-panel__state-text">{{ t('noComputeAssetsDesc') }}</text>
        </view>
      </view>

      <view class="asset-panel__actions">
        <view class="asset-panel__button primary" @tap="$emit('navigate', '/pages/market/index')">{{ t('openComputeMarket') }}</view>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AssetItem, AssetSummary } from '@/api/asset'
import AppIcon from '@/components/AppIcon.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import { useI18nStore } from '@/store/i18n'
import { fmtCardHours } from '@/utils/format'
import { localizeProductName } from '@/utils/localize-content'

const props = defineProps<{
  summary: AssetSummary | null
  items: AssetItem[]
  activeCount: number
  todayRevenue: number
  expiringCount: number
  tab: number
  loading: boolean
  listLoading: boolean
  error: boolean
}>()

defineEmits<{
  (event: 'navigate', url: string): void
  (event: 'retry'): void
  (event: 'update-tab', value: number): void
}>()

const i18n = useI18nStore()
const { t } = i18n
const tabLabels = computed(() => [t('running'), t('upcomingExpiry'), t('assetHistory')])
const emptyTitle = computed(() => props.tab === 1 ? t('noUpcomingExpiry') : props.tab === 2 ? t('noAssetHistory') : t('noComputeAssets'))

function remainingText(asset: AssetItem) {
  if (asset.status === 'sold') return t('sold')
  if (asset.status !== 'active') return t('expired')
  if (asset.purchase_type === 'holding') return t('holdingMode')
  return t('remainingDaysCount', { days: asset.remaining_days ?? 0 })
}

function earningsTone(value: number): string {
  return value > 0 ? 'positive' : value < 0 ? 'danger' : ''
}

function assetEarnings(asset: AssetItem): number {
  return Number(asset.purchase_type === 'holding' ? asset.pnl : asset.rebate_amount) || 0
}

function signedAssetEarnings(asset: AssetItem): string {
  const value = assetEarnings(asset)
  return `${value > 0 ? '+' : ''}${fmtCardHours(value)}`
}
</script>
