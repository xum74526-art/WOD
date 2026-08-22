<template>
  <view class="asset-panel">
    <view v-if="hostingStore.loading && !hostingStore.lastUpdated" class="asset-panel__skeleton" aria-hidden="true">
      <view class="asset-panel__skeleton-block" style="height: 300rpx"></view>
      <view v-for="n in 3" :key="n" class="asset-panel__skeleton-block"></view>
    </view>

    <view v-else-if="hostingStore.error && !hostingStore.lastUpdated" class="asset-panel__state">
      <view class="asset-panel__state-icon"><AppIcon name="settings" :size="54" /></view>
      <text class="asset-panel__state-title">{{ t('dataUnavailable') }}</text>
      <text class="asset-panel__state-text">{{ t('deviceStatusLoadFailedDesc') }}</text>
      <view class="asset-panel__state-action" @tap="hostingStore.refresh()">{{ t('retry') }}</view>
    </view>

    <template v-else>
      <view class="asset-panel__hero">
        <text class="asset-panel__eyebrow">{{ t('deviceStatus') }}</text>
        <view class="asset-panel__amount">
          <text class="asset-panel__amount-value">{{ hostingStore.totalDeviceCount }}</text>
          <text class="asset-panel__amount-unit">{{ t('devicesUnit') }}</text>
        </view>
        <text class="asset-panel__hero-note">{{ t('deviceStatusSummary') }}</text>
        <view class="asset-panel__metrics">
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value positive">{{ hostingStore.statusCounts.running }}</text>
            <text class="asset-panel__metric-label">{{ t('running') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value">{{ reviewCount }}</text>
            <text class="asset-panel__metric-label">{{ t('inReview') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value" :class="hostingStore.statusCounts.action_required ? 'danger' : ''">{{ hostingStore.statusCounts.action_required }}</text>
            <text class="asset-panel__metric-label">{{ t('actionRequired') }}</text>
          </view>
        </view>
      </view>

      <view class="asset-panel__section">
        <view class="asset-panel__section-head">
          <text class="asset-panel__section-title">{{ t('statusOverview') }}</text>
          <text class="asset-panel__section-meta">{{ statusLabel(selectedStatus) }}</text>
        </view>
        <scroll-view class="asset-panel__status-scroll" scroll-x :show-scrollbar="false">
          <view class="asset-panel__status-strip">
            <view
              v-for="status in statusOptions"
              :key="status.key"
              class="asset-panel__status-card"
              :class="{ active: selectedStatus === status.key }"
              role="button"
              tabindex="0"
              :aria-label="status.label"
              @tap="selectedStatus = status.key"
            >
              <text class="asset-panel__status-value" :class="status.tone">{{ hostingStore.statusCounts[status.key] }}</text>
              <text class="asset-panel__status-label">{{ status.label }}</text>
            </view>
          </view>
        </scroll-view>
      </view>

      <view class="asset-panel__section">
        <view class="asset-panel__section-head">
          <text class="asset-panel__section-title">{{ t('deviceList') }}</text>
          <text class="asset-panel__section-meta">{{ t('countItems', { count: filteredDevices.length }) }}</text>
        </view>

        <view v-if="filteredDevices.length" class="asset-panel__list">
          <view
            v-for="device in filteredDevices"
            :key="device.key"
            class="asset-panel__row"
            @tap="openDevice(device)"
          >
            <view class="asset-panel__row-icon"><AppIcon :name="device.source === 'supplier' ? 'gpu' : 'device'" :size="34" /></view>
            <view class="asset-panel__row-main">
              <text class="asset-panel__row-title">{{ deviceName(device) }}</text>
              <text class="asset-panel__row-meta">{{ device.model || t('deviceModelUnknown') }} · {{ device.location ? tr(device.location) : t('locationNotProvided') }}</text>
            </view>
            <view class="asset-panel__row-side">
              <StatusBadge :text="statusLabel(device.status)" :type="badgeType(device.status)" />
              <text class="asset-panel__row-hint">{{ t('countDevices', { count: device.count }) }}</text>
            </view>
          </view>
        </view>

        <view v-else class="asset-panel__state">
          <view class="asset-panel__state-icon"><AppIcon name="device" :size="50" /></view>
          <text class="asset-panel__state-title">{{ hostingStore.totalDeviceCount ? t('noDevicesInStatus') : t('noHostingDevices') }}</text>
          <text class="asset-panel__state-text">{{ hostingStore.totalDeviceCount ? t('chooseAnotherStatus') : t('noHostingDevicesDesc') }}</text>
        </view>
      </view>

      <view class="asset-panel__actions">
        <view class="asset-panel__button primary" @tap="$emit('navigate', '/pages/devices/index?status=' + selectedStatus)">{{ t('openFullDeviceList') }}</view>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useHostingStore, type HostingDeviceItem, type HostingDeviceStatus } from '@/store/hosting'
import { useI18nStore } from '@/store/i18n'
import { localizeProductName } from '@/utils/localize-content'

defineEmits<{ (event: 'navigate', url: string): void }>()

const hostingStore = useHostingStore()
const i18n = useI18nStore()
const { t, tr } = i18n
const selectedStatus = ref<HostingDeviceStatus>('running')
const reviewCount = computed(() => hostingStore.statusCounts.pending_review + hostingStore.statusCounts.reviewing + hostingStore.statusCounts.deploying)

const statusOptions = computed<Array<{ key: HostingDeviceStatus; label: string; tone: string }>>(() => [
  { key: 'pending_review', label: t('pendingReview'), tone: '' },
  { key: 'reviewing', label: t('underReview'), tone: '' },
  { key: 'deploying', label: t('deploying'), tone: 'warning' },
  { key: 'running', label: t('running'), tone: 'positive' },
  { key: 'action_required', label: t('actionRequired'), tone: 'danger' },
])

const filteredDevices = computed(() => hostingStore.devices.filter((device) => device.status === selectedStatus.value))

function statusLabel(status: HostingDeviceStatus) {
  const keys: Record<HostingDeviceStatus, string> = {
    pending_review: 'pendingReview',
    reviewing: 'underReview',
    deploying: 'deploying',
    running: 'running',
    action_required: 'actionRequired',
  }
  return t(keys[status])
}

function badgeType(status: HostingDeviceStatus): 'default' | 'running' | 'down' {
  if (status === 'running') return 'running'
  if (status === 'action_required') return 'down'
  return 'default'
}

function deviceName(device: HostingDeviceItem) {
  return device.source === 'application' ? t(device.name) : localizeProductName(device.name, i18n.lang)
}

function openDevice(device: HostingDeviceItem) {
  const url = device.source === 'supplier' ? '/pages/supplier/devices' : '/pages/compute-onboarding/index'
  uni.navigateTo({ url })
}
</script>
