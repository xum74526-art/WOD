<template>
  <view class="asset-panel">
    <view v-if="hostingStore.loading && !hostingStore.lastUpdated" class="asset-panel__skeleton" aria-hidden="true">
      <view class="asset-panel__skeleton-block" style="height: 300rpx"></view>
      <view v-for="n in 3" :key="n" class="asset-panel__skeleton-block"></view>
    </view>

    <view v-else-if="hostingStore.error && !hostingStore.lastUpdated" class="asset-panel__state">
      <view class="asset-panel__state-icon"><AppIcon name="bell" :size="54" /></view>
      <text class="asset-panel__state-title">{{ t('dataUnavailable') }}</text>
      <text class="asset-panel__state-text">{{ t('actionLoadFailedDesc') }}</text>
      <view class="asset-panel__state-action" @tap="hostingStore.refresh()">{{ t('retry') }}</view>
    </view>

    <template v-else>
      <view class="asset-panel__hero">
        <text class="asset-panel__eyebrow">{{ t('actionRequired') }}</text>
        <view class="asset-panel__amount">
          <text class="asset-panel__amount-value">{{ actionDevices.length }}</text>
          <text class="asset-panel__amount-unit">{{ t('itemsUnit') }}</text>
        </view>
        <text class="asset-panel__hero-note">{{ actionDevices.length ? t('actionRequiredHero') : t('allClear') }}</text>
        <view class="asset-panel__metrics">
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value" :class="rejectedCount ? 'danger' : ''">{{ rejectedCount }}</text>
            <text class="asset-panel__metric-label">{{ t('rejectedApplications') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value" :class="offlineCount ? 'danger' : ''">{{ offlineCount }}</text>
            <text class="asset-panel__metric-label">{{ t('offlineDevices') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value">{{ affectedCount }}</text>
            <text class="asset-panel__metric-label">{{ t('affectedDevices') }}</text>
          </view>
        </view>
      </view>

      <view class="asset-panel__section">
        <view class="asset-panel__section-head">
          <text class="asset-panel__section-title">{{ t('pendingActions') }}</text>
          <text class="asset-panel__section-meta">{{ t('countItems', { count: actionDevices.length }) }}</text>
        </view>

        <view v-if="actionDevices.length" class="asset-panel__list">
          <view
            v-for="device in actionDevices"
            :key="device.key"
            class="asset-panel__row"
            @tap="openAction(device)"
          >
            <view class="asset-panel__row-icon"><AppIcon name="bell" :size="34" /></view>
            <view class="asset-panel__row-main">
              <text class="asset-panel__row-title">{{ deviceName(device) }}</text>
              <text class="asset-panel__row-meta">{{ actionReason(device) }}</text>
            </view>
            <view class="asset-panel__row-side">
              <text class="asset-panel__row-value danger">{{ t('handleNow') }}</text>
              <text class="asset-panel__row-hint">{{ t('countDevices', { count: device.count }) }}</text>
            </view>
          </view>
        </view>

        <view v-else class="asset-panel__state">
          <view class="asset-panel__state-icon"><AppIcon name="check" :size="50" /></view>
          <text class="asset-panel__state-title">{{ t('noPendingActions') }}</text>
          <text class="asset-panel__state-text">{{ t('noPendingActionsDesc') }}</text>
        </view>
      </view>

      <view v-if="actionDevices.length" class="asset-panel__actions">
        <view class="asset-panel__button primary" @tap="$emit('navigate', '/pages/devices/index?status=action_required')">{{ t('viewAllActions') }}</view>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import { useHostingStore, type HostingDeviceItem } from '@/store/hosting'
import { useI18nStore } from '@/store/i18n'
import { localizeProductName } from '@/utils/localize-content'

const emit = defineEmits<{ (event: 'navigate', url: string): void }>()
const hostingStore = useHostingStore()
const i18n = useI18nStore()
const { t } = i18n

const actionDevices = computed(() => hostingStore.devices.filter((device) => device.status === 'action_required'))
const rejectedCount = computed(() => hostingStore.applications.filter((item) => item.status === 'rejected').length)
const offlineCount = computed(() => hostingStore.supplierDevices.filter((item) => item.status === 'offline' || item.list_status === 'off' || item.stock <= 0).length)
const affectedCount = computed(() => actionDevices.value.reduce((sum, device) => sum + device.count, 0))

function deviceName(device: HostingDeviceItem) {
  return device.source === 'application' ? t(device.name) : localizeProductName(device.name, i18n.lang)
}

function actionReason(device: HostingDeviceItem) {
  if (device.note) return t(device.note)
  return device.source === 'application' ? t('applicationRejected') : t('deviceRequiresAttention')
}

function openAction(device: HostingDeviceItem) {
  emit('navigate', device.source === 'supplier' ? '/pages/supplier/devices' : '/pages/compute-onboarding/index')
}
</script>
