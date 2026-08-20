<template>
  <view class="asset-panel">
    <view v-if="loading && !hasData" class="asset-panel__skeleton" aria-hidden="true">
      <view class="asset-panel__skeleton-block" style="height: 310rpx"></view>
      <view v-for="n in 3" :key="n" class="asset-panel__skeleton-block"></view>
    </view>

    <view v-else-if="error && !hasData" class="asset-panel__state">
      <view class="asset-panel__state-icon"><AppIcon name="revenue" :size="54" /></view>
      <text class="asset-panel__state-title">{{ t('dataUnavailable') }}</text>
      <text class="asset-panel__state-text">{{ t('earningsLoadFailedDesc') }}</text>
      <view class="asset-panel__state-action" @tap="$emit('retry')">{{ t('retry') }}</view>
    </view>

    <template v-else>
      <view class="asset-panel__hero">
        <text class="asset-panel__eyebrow">{{ t('availableBalance') }}</text>
        <view class="asset-panel__amount">
          <text class="asset-panel__amount-value">{{ fmtCHn(availableAmount) }}</text>
          <text class="asset-panel__amount-unit">{{ t('cardHour') }}</text>
        </view>
        <text class="asset-panel__hero-note">{{ t('hostingEarningsSummary') }}</text>
        <view class="asset-panel__metrics">
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value positive">{{ todayAmountText }}</text>
            <text class="asset-panel__metric-label">{{ t('todayIncome') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value">{{ totalAmountText }}</text>
            <text class="asset-panel__metric-label">{{ t('cumulativeRevenue') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value">{{ pendingAmountText }}</text>
            <text class="asset-panel__metric-label">{{ t('pendingSettlement') }}</text>
          </view>
        </view>
      </view>

      <view class="asset-panel__section">
        <view class="asset-panel__section-head">
          <text class="asset-panel__section-title">{{ t('earningsBreakdown') }}</text>
          <text class="asset-panel__section-meta">{{ t('realDataOnly') }}</text>
        </view>
        <view class="asset-panel__list">
          <view class="asset-panel__row" @tap="$emit('navigate', '/pages/revenue/index')">
            <view class="asset-panel__row-icon"><AppIcon name="gpu" :size="34" /></view>
            <view class="asset-panel__row-main">
              <text class="asset-panel__row-title">{{ t('computeRevenue') }}</text>
              <text class="asset-panel__row-meta">{{ t('computeRevenueDesc') }}</text>
            </view>
            <view class="asset-panel__row-side">
              <text class="asset-panel__row-value positive">{{ fmtCH(totalIncome) }}</text>
            </view>
          </view>
          <view class="asset-panel__row" @tap="openHostingRevenue">
            <view class="asset-panel__row-icon"><AppIcon name="device" :size="34" /></view>
            <view class="asset-panel__row-main">
              <text class="asset-panel__row-title">{{ t('hostingRevenue') }}</text>
              <text class="asset-panel__row-meta">{{ t('hostingRevenueDesc') }}</text>
            </view>
            <view class="asset-panel__row-side">
              <text class="asset-panel__row-value positive">{{ hostingRevenueText }}</text>
            </view>
          </view>
          <view class="asset-panel__row" @tap="$emit('navigate', '/pages/wallet/ledger')">
            <view class="asset-panel__row-icon"><AppIcon name="wallet" :size="34" /></view>
            <view class="asset-panel__row-main">
              <text class="asset-panel__row-title">{{ t('fundFlow') }}</text>
              <text class="asset-panel__row-meta">{{ t('viewAllTransactions') }}</text>
            </view>
            <view class="asset-panel__row-side"><AppIcon name="arrow-right" :size="26" /></view>
          </view>
        </view>
      </view>

      <view v-if="hostingStore.hostingRevenue == null" class="asset-panel__section">
        <view class="asset-panel__notice">{{ t('hostingRevenueUnavailableDesc') }}</view>
      </view>

      <view class="asset-panel__actions">
        <view class="asset-panel__button primary" @tap="openRevenueCenter">{{ t('openRevenueCenter') }}</view>
        <view class="asset-panel__button secondary" @tap="$emit('navigate', '/pages/wallet/index')">{{ t('viewWallet') }}</view>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import { useHostingStore } from '@/store/hosting'
import { useI18nStore } from '@/store/i18n'
import { fmtCH, fmtCHn } from '@/utils/format'

const props = defineProps<{
  walletBalance: number
  totalIncome: number
  pendingRevenue: number
  loading: boolean
  error: boolean
}>()

const emit = defineEmits<{
  (event: 'navigate', url: string): void
  (event: 'retry'): void
}>()

const hostingStore = useHostingStore()
const { t } = useI18nStore()
const hasData = computed(() => props.walletBalance > 0 || props.totalIncome > 0 || !!hostingStore.supplierWallet)
const availableAmount = computed(() => hostingStore.isApprovedMerchant ? hostingStore.supplierWallet?.available ?? 0 : props.walletBalance)
const todayAmountText = computed(() => hostingStore.isApprovedMerchant && hostingStore.supplierWallet ? fmtCHn(hostingStore.supplierWallet.today_revenue) : '--')
const totalAmountText = computed(() => hostingStore.isApprovedMerchant && hostingStore.supplierWallet ? fmtCHn(hostingStore.supplierWallet.total_revenue) : fmtCHn(props.totalIncome))
const pendingAmountText = computed(() => hostingStore.isApprovedMerchant && hostingStore.supplierWallet ? fmtCHn(hostingStore.supplierWallet.pending_amount) : fmtCHn(props.pendingRevenue))
const hostingRevenueText = computed(() => hostingStore.hostingRevenue == null ? '--' : fmtCH(hostingStore.hostingRevenue))

function openHostingRevenue() {
  if (hostingStore.isApprovedMerchant) emit('navigate', '/pages/supplier/revenue')
}

function openRevenueCenter() {
  emit('navigate', hostingStore.isApprovedMerchant ? '/pages/supplier/revenue' : '/pages/revenue/index')
}
</script>
