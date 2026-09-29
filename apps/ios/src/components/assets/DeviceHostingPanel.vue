<template>
  <view class="asset-panel">
    <view v-if="hostingStore.loading && !hostingStore.lastUpdated" class="asset-panel__skeleton" aria-hidden="true">
      <view class="asset-panel__skeleton-block" style="height: 320rpx"></view>
      <view v-for="n in 3" :key="n" class="asset-panel__skeleton-block"></view>
    </view>

    <view v-else-if="hostingStore.error && !hostingStore.lastUpdated" class="asset-panel__state">
      <view class="asset-panel__state-icon"><AppIcon name="device" :size="54" /></view>
      <text class="asset-panel__state-title">{{ t('dataUnavailable') }}</text>
      <text class="asset-panel__state-text">{{ t('hostingLoadFailedDesc') }}</text>
      <view class="asset-panel__state-action" @tap="hostingStore.refresh()">{{ t('retry') }}</view>
    </view>

    <template v-else>
      <view class="asset-panel__hero">
        <text class="asset-panel__eyebrow">{{ roleLabel }} · {{ qualificationLabel }}</text>
        <view class="asset-panel__amount">
          <text class="asset-panel__amount-value">{{ hostingStore.totalDeviceCount }}</text>
          <text class="asset-panel__amount-unit">{{ t('devicesUnit') }}</text>
        </view>
        <text class="asset-panel__hero-note">{{ hostingHeroNote }}</text>
        <view class="asset-panel__metrics">
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value positive">{{ hostingStore.runningCount }}</text>
            <text class="asset-panel__metric-label">{{ t('running') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value">{{ reviewCount }}</text>
            <text class="asset-panel__metric-label">{{ t('inReview') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value" :class="hostingStore.actionRequiredCount ? 'danger' : ''">{{ hostingStore.actionRequiredCount }}</text>
            <text class="asset-panel__metric-label">{{ t('actionRequired') }}</text>
          </view>
        </view>
      </view>

      <view v-if="hostingStore.hostingRole === 'viewer'" class="asset-panel__section">
        <view class="asset-panel__notice">{{ t('verifyBeforeHosting') }}</view>
      </view>

      <view class="asset-panel__section">
        <view class="asset-panel__section-head">
          <text class="asset-panel__section-title">{{ t('hostingOverview') }}</text>
          <text class="asset-panel__section-meta">{{ t('dataUpdated') }}</text>
        </view>
        <view class="asset-panel__summary">
          <view class="asset-panel__summary-item">
            <text class="asset-panel__summary-label">{{ t('pendingReview') }}</text>
            <text class="asset-panel__summary-value">{{ hostingStore.statusCounts.pending_review }}</text>
          </view>
          <view class="asset-panel__summary-item">
            <text class="asset-panel__summary-label">{{ t('underReview') }}</text>
            <text class="asset-panel__summary-value">{{ hostingStore.statusCounts.reviewing }}</text>
          </view>
          <view class="asset-panel__summary-item">
            <text class="asset-panel__summary-label">{{ t('deploying') }}</text>
            <text class="asset-panel__summary-value">{{ hostingStore.statusCounts.deploying }}</text>
          </view>
          <view class="asset-panel__summary-item">
            <text class="asset-panel__summary-label">{{ t('totalHostingRevenue') }}</text>
            <text class="asset-panel__summary-value positive">{{ hostingRevenueText }}</text>
          </view>
        </view>
      </view>

      <view class="asset-panel__section">
        <view class="asset-panel__section-head">
          <text class="asset-panel__section-title">{{ t('hostingDevices') }}</text>
          <text class="asset-panel__section-meta">{{ hostingStore.devices.length ? t('showingLatest', { count: Math.min(hostingStore.devices.length, 4) }) : t('noData') }}</text>
        </view>

        <view v-if="hostingStore.devices.length" class="asset-panel__list">
          <view
            v-for="device in hostingStore.devices.slice(0, 4)"
            :key="device.key"
            class="asset-panel__row"
            @tap="openDevice(device)"
          >
            <view class="asset-panel__row-icon"><AppIcon :name="device.source === 'supplier' ? 'gpu' : 'device'" :size="34" /></view>
            <view class="asset-panel__row-main">
              <text class="asset-panel__row-title">{{ deviceName(device) }}</text>
              <text class="asset-panel__row-meta">{{ device.model || t('deviceModelUnknown') }} · {{ t('countDevices', { count: device.count }) }}</text>
            </view>
            <view class="asset-panel__row-side">
              <StatusBadge :text="statusLabel(device.status)" :type="badgeType(device.status)" />
            </view>
          </view>
        </view>

        <view v-else class="asset-panel__state">
          <view class="asset-panel__state-icon"><AppIcon name="device" :size="50" /></view>
          <text class="asset-panel__state-title">{{ t('noHostingDevices') }}</text>
          <text class="asset-panel__state-text">{{ emptyDescription }}</text>
        </view>
      </view>

      <view class="asset-panel__actions">
        <view class="asset-panel__button primary" @tap="openPrimaryAction">{{ primaryActionLabel }}</view>
        <view v-if="hostingStore.totalDeviceCount" class="asset-panel__button secondary" @tap="openStatus">{{ t('viewDeviceStatus') }}</view>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useHostingStore, type HostingDeviceItem, type HostingDeviceStatus } from '@/store/hosting'
import { useI18nStore } from '@/store/i18n'
import { useUserStore } from '@/store/user'
import { formatCardHourCurrency } from '@/utils/format'
import { localizeProductName } from '@/utils/localize-content'

const emit = defineEmits<{
  (event: 'navigate', url: string): void
  (event: 'select-panel', key: 'device-status'): void
}>()

const hostingStore = useHostingStore()
const userStore = useUserStore()
const i18n = useI18nStore()
const { t } = i18n

const reviewCount = computed(() => hostingStore.statusCounts.pending_review + hostingStore.statusCounts.reviewing + hostingStore.statusCounts.deploying)
const roleLabel = computed(() => t(hostingStore.hostingRole === 'merchant_operator' ? 'merchantOperator' : hostingStore.hostingRole === 'personal_owner' ? 'personalOwner' : 'hostingVisitor'))
const qualificationLabel = computed(() => t(hostingStore.verification?.status === 'verified' ? 'verified' : hostingStore.verification?.status === 'pending' ? 'verificationPending' : 'notVerified'))
const hostingHeroNote = computed(() => t(hostingStore.hostingRole === 'merchant_operator' ? 'merchantHostingHero' : hostingStore.hostingRole === 'personal_owner' ? 'personalHostingHero' : 'viewerHostingHero'))
const hostingRevenueText = computed(() => hostingStore.hostingRevenue == null ? '--' : formatCardHourCurrency(hostingStore.hostingRevenue))
const emptyDescription = computed(() => t(hostingStore.hostingRole === 'viewer' ? 'verifyBeforeHosting' : 'noHostingDevicesDesc'))
const primaryActionLabel = computed(() => {
  if (!userStore.isLogin) return t('loginNow')
  if (hostingStore.hostingRole === 'merchant_operator') return t('manageDeviceFleet')
  if (hostingStore.verification?.status !== 'verified') return t('verifyNow')
  if (hostingStore.totalDeviceCount) return t('manageDevices')
  return t('addDevice')
})

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
  emit('navigate', device.source === 'supplier' ? '/pages/supplier/devices' : '/pages/compute-onboarding/index')
}

function openPrimaryAction() {
  if (!userStore.isLogin) emit('navigate', '/pages/login/index')
  else if (hostingStore.hostingRole === 'merchant_operator') emit('navigate', '/pages/supplier/devices')
  else if (hostingStore.verification?.status !== 'verified') emit('navigate', '/pages/verification/index')
  else emit('navigate', '/pages/compute-onboarding/index')
}

function openStatus() {
  emit('select-panel', 'device-status')
}
</script>
