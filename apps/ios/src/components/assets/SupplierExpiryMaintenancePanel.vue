<template>
  <view class="asset-panel">
    <view v-if="hostingStore.loading && !hostingStore.lastUpdated" class="asset-panel__skeleton" aria-hidden="true">
      <view class="asset-panel__skeleton-block" style="height: 300rpx"></view>
      <view v-for="n in 2" :key="n" class="asset-panel__skeleton-block"></view>
    </view>

    <view v-else-if="hostingStore.error && !hostingStore.lastUpdated" class="asset-panel__state">
      <view class="asset-panel__state-icon"><AppIcon name="settings" :size="54" /></view>
      <text class="asset-panel__state-title">{{ t('dataUnavailable') }}</text>
      <text class="asset-panel__state-text">{{ t('supplierLoadFailedDesc') }}</text>
      <view class="asset-panel__state-action" @tap="hostingStore.refresh()">{{ t('retry') }}</view>
    </view>

    <template v-else>
      <view class="asset-panel__hero">
        <text class="asset-panel__eyebrow">{{ t('expiryMaintenance') }}</text>
        <view class="asset-panel__amount">
          <text class="asset-panel__amount-value">--</text>
          <text class="asset-panel__amount-unit">{{ t('maintenancePlan') }}</text>
        </view>
        <text class="asset-panel__hero-note">{{ t('merchantExpiryMaintenanceSummary') }}</text>
        <view class="asset-panel__metrics">
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value">--</text>
            <text class="asset-panel__metric-label">{{ t('expiringIn3Days') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value">--</text>
            <text class="asset-panel__metric-label">{{ t('expiringIn7Days') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value">--</text>
            <text class="asset-panel__metric-label">{{ t('maintenancePlan') }}</text>
          </view>
        </view>
      </view>

      <view class="asset-panel__section">
        <view class="asset-panel__section-head">
          <text class="asset-panel__section-title">{{ t('upcomingExpiry') }}</text>
          <text class="asset-panel__section-meta">{{ t('notAvailable') }}</text>
        </view>
        <view class="asset-panel__notice">{{ t('merchantExpiryUnavailableDesc') }}</view>
      </view>

      <view class="asset-panel__section">
        <view class="asset-panel__section-head">
          <text class="asset-panel__section-title">{{ t('maintenancePlan') }}</text>
          <text class="asset-panel__section-meta">{{ t('notAvailable') }}</text>
        </view>
        <view class="asset-panel__notice">{{ t('noMaintenancePlanDesc') }}</view>
      </view>

      <view class="asset-panel__actions">
        <view class="asset-panel__button primary" @tap="$emit('navigate', '/pages/supplier/devices')">{{ t('openAssetManagement') }}</view>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import AppIcon from '@/components/AppIcon.vue'
import { useHostingStore } from '@/store/hosting'
import { useI18nStore } from '@/store/i18n'

defineEmits<{ (event: 'navigate', url: string): void }>()

const hostingStore = useHostingStore()
const { t } = useI18nStore()
</script>
