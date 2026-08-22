<template>
  <view class="page">
    <AppNavBar :title="t('deviceStatus')">
      <template #right>
        <text class="nav-action" @tap="openHosting">{{ t('deviceHosting') }}</text>
      </template>
    </AppNavBar>

    <view class="shell">
      <view class="section-heading">
        <text class="section-title">{{ t('statusOverview') }}</text>
        <text class="section-meta">{{ t('countDevices', { count: hostingStore.totalDeviceCount }) }}</text>
      </view>

      <scroll-view class="status-scroll" scroll-x :show-scrollbar="false">
        <view class="status-strip">
          <view
            v-for="status in statusOptions"
            :key="status.key"
            class="status-card"
            :class="{ active: selectedStatus === status.key }"
            role="button"
            tabindex="0"
            :aria-label="status.label"
            @tap="selectedStatus = status.key"
          >
            <text class="status-count" :class="status.tone">{{ hostingStore.statusCounts[status.key] }}</text>
            <text class="status-label">{{ status.label }}</text>
          </view>
        </view>
      </scroll-view>

      <view v-if="hostingStore.loading && !hostingStore.lastUpdated" class="device-list">
        <view v-for="n in 3" :key="n" class="card skeleton-device"></view>
      </view>

      <view v-else-if="hostingStore.error && !hostingStore.lastUpdated" class="card state-card">
        <text class="state-title">{{ t('dataUnavailable') }}</text>
        <view class="state-action" @tap="hostingStore.refresh()">{{ t('retry') }}</view>
      </view>

      <view v-else-if="!filteredDevices.length" class="card empty-card">
        <EmptyState :text="hostingStore.totalDeviceCount ? t('noDevicesInStatus') : t('noHostingDevices')">
          <AppIcon name="device" :size="52" />
        </EmptyState>
        <text v-if="!hostingStore.totalDeviceCount" class="empty-description">{{ t('noHostingDevicesDesc') }}</text>
        <view v-if="!hostingStore.totalDeviceCount" class="empty-action" @tap="openHosting">{{ hostingEntryLabel }}</view>
      </view>

      <view v-else class="device-list">
        <view
          v-for="device in filteredDevices"
          :key="device.key"
          class="card device-row"
          @tap="openDevice(device)"
        >
          <view class="device-head">
            <view class="device-icon"><AppIcon :name="device.source === 'supplier' ? 'gpu' : 'device'" :size="36" /></view>
            <view class="device-heading">
              <view class="name-row">
                <text class="device-name">{{ deviceName(device) }}</text>
                <StatusBadge :text="statusLabel(device.status)" :type="badgeType(device.status)" />
              </view>
              <text class="device-model">{{ device.model }} · {{ t('countDevices', { count: device.count }) }}</text>
            </view>
          </view>

          <view class="device-detail">
            <view class="detail-row">
              <text class="detail-label">{{ t('hostingApplication') }}</text>
              <text class="detail-value">#{{ device.sourceId }}</text>
            </view>
            <view v-if="device.location" class="detail-row">
              <text class="detail-label">{{ t('region') }}</text>
              <text class="detail-value">{{ tr(device.location) }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">{{ t('sourceLabel') }}</text>
              <text class="detail-value">{{ t(device.source === 'supplier' ? 'deviceSourceMerchant' : 'deviceSourcePersonal') }}</text>
            </view>
          </view>

          <view class="device-footer">
            <text class="status-description">{{ statusDescription(device) }}</text>
            <view class="row-action">
              <text>{{ t('openDevice') }}</text>
              <AppIcon name="arrow-right" :size="24" />
            </view>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import AppIcon from '@/components/AppIcon.vue'
import AppNavBar from '@/components/AppNavBar.vue'
import EmptyState from '@/components/EmptyState.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useHostingStore, type HostingDeviceItem, type HostingDeviceStatus } from '@/store/hosting'
import { useI18nStore } from '@/store/i18n'
import { localizeProductName } from '@/utils/localize-content'
import { navigateTo as nav } from '@/utils/nav'

const hostingStore = useHostingStore()
const i18n = useI18nStore()
const { t, tr } = i18n
const selectedStatus = ref<HostingDeviceStatus>('running')

const statusOptions = computed<Array<{ key: HostingDeviceStatus; label: string; tone: string }>>(() => [
  { key: 'pending_review', label: t('pendingReview'), tone: '' },
  { key: 'reviewing', label: t('underReview'), tone: '' },
  { key: 'deploying', label: t('deploying'), tone: 'warning' },
  { key: 'running', label: t('running'), tone: 'positive' },
  { key: 'action_required', label: t('actionRequired'), tone: 'danger' },
])

const filteredDevices = computed(() => hostingStore.devices.filter((device) => device.status === selectedStatus.value))
const hostingEntryLabel = computed(() => hostingStore.verification?.status === 'verified' ? t('startHosting') : t('verifyNow'))

function statusLabel(status: HostingDeviceStatus) {
  const key: Record<HostingDeviceStatus, string> = {
    pending_review: 'pendingReview',
    reviewing: 'underReview',
    deploying: 'deploying',
    running: 'running',
    action_required: 'actionRequired',
  }
  return t(key[status])
}

function badgeType(status: HostingDeviceStatus): 'default' | 'running' | 'down' {
  if (status === 'running') return 'running'
  if (status === 'action_required') return 'down'
  return 'default'
}

function statusDescription(device: HostingDeviceItem) {
  if (device.source === 'supplier') {
    if (device.note) return t(device.note)
    return t('deviceRunningNormally')
  }
  const key: Record<HostingDeviceStatus, string> = {
    pending_review: 'applicationSubmitted',
    reviewing: 'applicationContacted',
    deploying: 'applicationApproved',
    running: 'deviceRunningNormally',
    action_required: 'applicationRejected',
  }
  return t(key[device.status])
}

function deviceName(device: HostingDeviceItem) {
  return device.source === 'application'
    ? t(device.name)
    : localizeProductName(device.name, i18n.lang)
}

function openDevice(device: HostingDeviceItem) {
  nav(device.source === 'supplier' ? '/pages/supplier/devices' : '/pages/compute-onboarding/index')
}

function openHosting() {
  if (hostingStore.isApprovedMerchant) nav('/pages/supplier/dashboard')
  else if (hostingStore.verification?.status === 'verified') nav('/pages/compute-onboarding/index')
  else nav('/pages/verification/index')
}

onLoad((options) => {
  const requested = options?.status as HostingDeviceStatus | undefined
  if (requested && ['pending_review', 'reviewing', 'deploying', 'running', 'action_required'].includes(requested)) {
    selectedStatus.value = requested
  }
})

onShow(() => hostingStore.refresh())
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; min-height: 100dvh; background: var(--bg); }
.shell { padding: 12rpx 32rpx calc(132rpx + var(--safe-bottom)); }
.nav-action { color: var(--primary); font-size: 23rpx; font-weight: 600; }
.section-heading { display: flex; align-items: baseline; justify-content: space-between; margin: 18rpx 0 20rpx; }
.section-title { color: var(--text); font-size: 32rpx; font-weight: 720; }
.section-meta { color: var(--text-sub); font-size: 22rpx; }
.status-scroll { width: calc(100% + 64rpx); margin-left: -32rpx; margin-bottom: 28rpx; white-space: nowrap; }
.status-strip { display: inline-flex; gap: 14rpx; padding: 0 32rpx 6rpx; }
.status-card { width: 178rpx; min-height: 148rpx; box-sizing: border-box; padding: 24rpx; border-radius: 22rpx; border: 1rpx solid var(--card-border); background: var(--card); box-shadow: var(--shadow); }
.status-card.active { border-color: var(--primary); background: var(--primary-soft); }
.status-card:active { transform: scale(0.98); }
.status-count { display: block; color: var(--text); font-size: 40rpx; font-weight: 780; font-variant-numeric: tabular-nums; }
.status-count.positive { color: var(--up); }
.status-count.warning { color: #b45309; }
.status-count.danger { color: var(--down); }
.status-label { display: block; color: var(--text-sub); font-size: 22rpx; margin-top: 10rpx; }
.status-card.active .status-label { color: var(--text); font-weight: 600; }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--card-border); box-shadow: var(--shadow); }
.device-list { display: flex; flex-direction: column; gap: 16rpx; }
.device-row { padding: 28rpx; }
.device-row:active { transform: scale(0.992); }
.device-head { display: flex; align-items: flex-start; gap: 18rpx; }
.device-icon { width: 68rpx; height: 68rpx; border-radius: 17rpx; background: var(--primary-soft); color: var(--primary); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.device-heading { min-width: 0; flex: 1; }
.name-row { display: flex; align-items: center; gap: 12rpx; }
.device-name { min-width: 0; color: var(--text); font-size: 29rpx; font-weight: 680; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.device-model { display: block; color: var(--text-sub); font-size: 22rpx; margin-top: 8rpx; }
.device-detail { margin-top: 24rpx; padding: 18rpx 0; border-top: 1rpx solid var(--divider); border-bottom: 1rpx solid var(--divider); }
.detail-row { display: flex; align-items: center; justify-content: space-between; gap: 24rpx; min-height: 44rpx; }
.detail-label { color: var(--text-sub); font-size: 22rpx; }
.detail-value { max-width: 64%; color: var(--text); font-size: 22rpx; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.device-footer { display: flex; align-items: center; justify-content: space-between; gap: 18rpx; margin-top: 20rpx; }
.status-description { min-width: 0; flex: 1; color: var(--text-sub); font-size: 22rpx; line-height: 1.45; }
.row-action { flex-shrink: 0; min-height: 64rpx; display: flex; align-items: center; gap: 4rpx; color: var(--primary); font-size: 22rpx; font-weight: 600; }
.empty-card { padding: 0 32rpx 36rpx; text-align: center; }
.empty-description { display: block; color: var(--text-sub); font-size: 23rpx; line-height: 1.55; margin: -82rpx 24rpx 28rpx; }
.empty-action { min-height: 76rpx; border-radius: 18rpx; background: var(--primary); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 25rpx; font-weight: 650; }
.state-card { padding: 56rpx 32rpx; text-align: center; }
.state-title { display: block; color: var(--text-sub); font-size: 25rpx; }
.state-action { display: inline-flex; min-height: 68rpx; padding: 0 28rpx; align-items: center; justify-content: center; border-radius: 16rpx; color: var(--primary); border: 1rpx solid var(--primary); font-size: 23rpx; margin-top: 22rpx; }
.skeleton-device { height: 260rpx; background: linear-gradient(90deg, var(--card), var(--bg-2), var(--card)); background-size: 200% 100%; animation: skeleton-shift 1.2s ease infinite; }
@keyframes skeleton-shift { from { background-position: 100% 0; } to { background-position: -100% 0; } }
@media (prefers-reduced-motion: reduce) {
  .skeleton-device { animation: none; }
  .status-card, .device-row { transition: none; }
}
</style>
