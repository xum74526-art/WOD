<template>
  <view class="asset-panel">
    <view v-if="hostingStore.loading && !hostingStore.lastUpdated" class="asset-panel__skeleton" aria-hidden="true">
      <view class="asset-panel__skeleton-block" style="height: 310rpx"></view>
      <view v-for="n in 3" :key="n" class="asset-panel__skeleton-block"></view>
    </view>

    <view v-else-if="hostingStore.error && !hostingStore.lastUpdated" class="asset-panel__state">
      <view class="asset-panel__state-icon"><AppIcon name="gpu" :size="54" /></view>
      <text class="asset-panel__state-title">{{ t('dataUnavailable') }}</text>
      <text class="asset-panel__state-text">{{ t('supplierLoadFailedDesc') }}</text>
      <view class="asset-panel__state-action" @tap="hostingStore.refresh()">{{ t('retry') }}</view>
    </view>

    <template v-else>
      <view class="asset-panel__hero">
        <text class="asset-panel__eyebrow">{{ t('merchantResources') }}</text>
        <view class="asset-panel__amount">
          <text class="asset-panel__amount-value">{{ totalStock }}</text>
          <text class="asset-panel__amount-unit">{{ t('devicesUnit') }}</text>
        </view>
        <text class="asset-panel__hero-note">{{ t('merchantComputeAssetsSummary') }}</text>
        <view class="asset-panel__metrics">
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value positive">{{ listedCount }}</text>
            <text class="asset-panel__metric-label">{{ t('onSale2') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value" :class="delistedCount ? 'warning' : ''">{{ delistedCount }}</text>
            <text class="asset-panel__metric-label">{{ t('offShelf') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value">{{ hostingStore.supplierDevices.length }}</text>
            <text class="asset-panel__metric-label">{{ t('resourceSpecifications') }}</text>
          </view>
        </view>
      </view>

      <view class="asset-panel__section">
        <view class="asset-panel__section-head">
          <text class="asset-panel__section-title">{{ t('computeResourceList') }}</text>
          <text class="asset-panel__section-meta">{{ t('countItems', { count: hostingStore.supplierDevices.length }) }}</text>
        </view>
        <view v-if="hostingStore.supplierDevices.length" class="asset-panel__list">
          <view
            v-for="device in hostingStore.supplierDevices"
            :key="device.id"
            class="asset-panel__row"
            @tap="$emit('navigate', '/pages/supplier/devices')"
          >
            <view class="asset-panel__row-icon"><AppIcon name="gpu" :size="34" /></view>
            <view class="asset-panel__row-main">
              <text class="asset-panel__row-title">{{ localizeProductName(device.name, i18n.lang) }}</text>
              <text class="asset-panel__row-meta">{{ device.gpu_model }} · {{ t('countDevices', { count: device.stock }) }} · {{ locationText(device) }}</text>
            </view>
            <view class="asset-panel__row-side">
              <text class="asset-panel__row-value positive">{{ fmtCH(device.price) }}/h</text>
              <text class="asset-panel__row-hint">{{ t(device.list_status === 'on' ? 'onSale2' : 'offShelf') }}</text>
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
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { SupplierDeviceItem } from '@/api/supplier'
import AppIcon from '@/components/AppIcon.vue'
import { useHostingStore } from '@/store/hosting'
import { useI18nStore } from '@/store/i18n'
import { fmtCH } from '@/utils/format'
import { localizeProductName } from '@/utils/localize-content'

defineEmits<{ (event: 'navigate', url: string): void }>()

const hostingStore = useHostingStore()
const i18n = useI18nStore()
const { t, tr } = i18n

const listedCount = computed(() => hostingStore.supplierDevices.filter((device) => device.list_status === 'on').length)
const delistedCount = computed(() => hostingStore.supplierDevices.filter((device) => device.list_status !== 'on').length)
const totalStock = computed(() => hostingStore.supplierDevices.reduce((sum, device) => sum + Math.max(Number(device.stock) || 0, 0), 0))

function locationText(device: SupplierDeviceItem) {
  const location = [device.region, device.city].filter((value) => value && value !== '-').join(' ')
  return location ? tr(location) : t('locationNotProvided')
}
</script>
