<template>
  <view class="asset-panel">
    <view v-if="hostingStore.loading && !hostingStore.lastUpdated" class="asset-panel__skeleton" aria-hidden="true">
      <view class="asset-panel__skeleton-block" style="height: 310rpx"></view>
      <view v-for="n in 3" :key="n" class="asset-panel__skeleton-block"></view>
    </view>

    <view v-else-if="hostingStore.error && !hostingStore.lastUpdated" class="asset-panel__state">
      <view class="asset-panel__state-icon"><AppIcon name="wallet" :size="54" /></view>
      <text class="asset-panel__state-title">{{ t('dataUnavailable') }}</text>
      <text class="asset-panel__state-text">{{ t('supplierLoadFailedDesc') }}</text>
      <view class="asset-panel__state-action" @tap="hostingStore.refresh()">{{ t('retry') }}</view>
    </view>

    <template v-else>
      <view class="asset-panel__hero">
        <text class="asset-panel__eyebrow">{{ t('merchantAvailableBalance') }}</text>
        <view class="asset-panel__amount">
          <text class="asset-panel__amount-value">{{ availableText }}</text>
          <text class="asset-panel__amount-unit">{{ t('cardHour') }}</text>
        </view>
        <text class="asset-panel__hero-note">{{ t('merchantAssetOverviewSummary') }}</text>
        <view class="asset-panel__metrics">
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value positive">{{ todayRevenueText }}</text>
            <text class="asset-panel__metric-label">{{ t('todayIncome2') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value positive">{{ totalRevenueText }}</text>
            <text class="asset-panel__metric-label">{{ t('totalIncome') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value">{{ hostingStore.supplierDevices.length }}</text>
            <text class="asset-panel__metric-label">{{ t('merchantResources') }}</text>
          </view>
        </view>
      </view>

      <view class="asset-panel__section">
        <view class="asset-panel__section-head">
          <text class="asset-panel__section-title">{{ t('assetComposition') }}</text>
          <text class="asset-panel__section-meta">{{ t('realDataOnly') }}</text>
        </view>
        <view class="asset-panel__summary">
          <view class="asset-panel__summary-item">
            <text class="asset-panel__summary-label">{{ t('onSale2') }}</text>
            <text class="asset-panel__summary-value">{{ listedCount }}</text>
          </view>
          <view class="asset-panel__summary-item">
            <text class="asset-panel__summary-label">{{ t('offShelf') }}</text>
            <text class="asset-panel__summary-value">{{ delistedCount }}</text>
          </view>
          <view class="asset-panel__summary-item">
            <text class="asset-panel__summary-label">{{ t('totalStock') }}</text>
            <text class="asset-panel__summary-value">{{ totalStock }}</text>
          </view>
          <view class="asset-panel__summary-item">
            <text class="asset-panel__summary-label">{{ t('pendingSettlement') }}</text>
            <text class="asset-panel__summary-value">{{ pendingText }}</text>
          </view>
        </view>
      </view>

      <view class="asset-panel__section">
        <view class="asset-panel__section-head">
          <text class="asset-panel__section-title">{{ t('recentAssets') }}</text>
          <text class="asset-panel__section-meta">{{ t('countItems', { count: hostingStore.supplierDevices.length }) }}</text>
        </view>
        <view v-if="hostingStore.supplierDevices.length" class="asset-panel__list">
          <view
            v-for="device in hostingStore.supplierDevices.slice(0, 4)"
            :key="device.id"
            class="asset-panel__row"
            @tap="$emit('navigate', '/pages/supplier/devices')"
          >
            <view class="asset-panel__row-icon"><AppIcon name="gpu" :size="34" /></view>
            <view class="asset-panel__row-main">
              <text class="asset-panel__row-title">{{ localizeProductName(device.name, i18n.lang) }}</text>
              <text class="asset-panel__row-meta">{{ device.gpu_model }} · {{ t('countDevices', { count: device.stock }) }}</text>
            </view>
            <view class="asset-panel__row-side">
              <text class="asset-panel__row-value" :class="device.list_status === 'on' ? 'positive' : ''">
                {{ t(device.list_status === 'on' ? 'onSale2' : 'offShelf') }}
              </text>
            </view>
          </view>
        </view>
        <view v-else class="asset-panel__state">
          <view class="asset-panel__state-icon"><AppIcon name="gpu" :size="50" /></view>
          <text class="asset-panel__state-title">{{ t('noMerchantResources') }}</text>
          <text class="asset-panel__state-text">{{ t('noMerchantResourcesDesc') }}</text>
        </view>
      </view>

      <view class="asset-panel__actions">
        <view class="asset-panel__button primary" @tap="$emit('navigate', '/pages/supplier/devices')">{{ t('openAssetManagement') }}</view>
        <view class="asset-panel__button secondary" @tap="$emit('navigate', '/pages/supplier/revenue')">{{ t('revenueSettle') }}</view>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import { useHostingStore } from '@/store/hosting'
import { useI18nStore } from '@/store/i18n'
import { fmtCHn } from '@/utils/format'
import { localizeProductName } from '@/utils/localize-content'

defineEmits<{ (event: 'navigate', url: string): void }>()

const hostingStore = useHostingStore()
const i18n = useI18nStore()
const { t } = i18n

const listedCount = computed(() => hostingStore.supplierDevices.filter((device) => device.list_status === 'on').length)
const delistedCount = computed(() => hostingStore.supplierDevices.filter((device) => device.list_status !== 'on').length)
const totalStock = computed(() => hostingStore.supplierDevices.reduce((sum, device) => sum + Math.max(Number(device.stock) || 0, 0), 0))
const availableText = computed(() => hostingStore.supplierWallet ? fmtCHn(hostingStore.supplierWallet.available) : '--')
const todayRevenueText = computed(() => hostingStore.supplierWallet ? fmtCHn(hostingStore.supplierWallet.today_revenue) : '--')
const totalRevenueText = computed(() => hostingStore.supplierWallet ? fmtCHn(hostingStore.supplierWallet.total_revenue) : '--')
const pendingText = computed(() => hostingStore.supplierWallet ? fmtCHn(hostingStore.supplierWallet.pending_amount) : '--')
</script>
