<template>
  <view class="page">
    <AppNavBar :title="t('k_0aeca07a')" />
    <view class="shell">
      <view class="read-only-note">
        <text class="read-only-title">{{ t('mobileMerchantReadOnlyTitle') }}</text>
        <text class="read-only-desc">{{ t('mobileMerchantReadOnlyHint') }}</text>
      </view>
      <view v-if="loadError" class="load-error">
        <text>{{ t('supplierLoadFailedDesc') }}</text>
        <text class="load-retry" @tap="load">{{ t('retry') }}</text>
      </view>
      <SectionHeader :title="t('k_07ec72a7')" />
      <view class="card form">
        <view class="field"><text class="flabel">{{ t('k_f47e2736') }}</text><text class="fvalue">{{ info.company_name || t('notAvailableShort') }}</text></view>
        <view class="field"><text class="flabel">{{ t('k_52409da5') }}</text><text class="fvalue">{{ info.contact || t('notAvailableShort') }}</text></view>
        <view class="field"><text class="flabel">{{ t('k_09a1f698') }}</text><text class="fvalue">{{ info.phone || t('notAvailableShort') }}</text></view>
        <view class="field"><text class="flabel">{{ t('k_65d3ab77') }}</text><text class="fvalue">{{ info.region || t('notAvailableShort') }}</text></view>
        <view class="field"><text class="flabel">{{ t('k_a784c811') }}</text><text class="fvalue multiline">{{ info.desc || t('notAvailableShort') }}</text></view>
      </view>

      <SectionHeader :title="t('k_748a4837')" />
      <view class="notification-status">
        <view class="status-dot"></view>
        <view class="status-copy">
          <text class="status-title">{{ t('inAppNotificationsEnabled') }}</text>
          <text class="status-desc">{{ delivery?.system_push_configured ? t('systemPushConfigured') : t('systemPushPending') }}</text>
        </view>
      </view>
      <view class="card menu">
        <view v-if="notificationLoadError" class="notification-error">
          <text>{{ t('notificationPreferencesLoadFailed') }}</text>
          <text class="load-retry" @tap="loadNotificationSettings">{{ t('retry') }}</text>
        </view>
        <template v-else>
          <view class="m-item">
            <text>{{ t('k_9d8efc4c') }}</text>
            <text class="preference-value">{{ t(notificationPrefs.order_enabled ? 'enabled' : 'disabled') }}</text>
          </view>
          <view class="m-item">
            <text>{{ t('k_01e08c5a') }}</text>
            <text class="preference-value">{{ t(notificationPrefs.device_enabled ? 'enabled' : 'disabled') }}</text>
          </view>
          <view class="m-item">
            <text>{{ t('k_f2c846ec') }}</text>
            <text class="preference-value">{{ t(notificationPrefs.revenue_enabled ? 'enabled' : 'disabled') }}</text>
          </view>
        </template>
      </view>

      <SectionHeader :title="t('k_7035c62f')" />
      <view class="card menu">
        <view class="m-item danger" @tap="switchBack"><text>{{ t('k_6a3c1f96') }}</text></view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { request } from '@/api/request'
import { useUserStore } from '@/store/user'
import {
  getNotificationPreferences,
  type NotificationDeliveryStatus,
  type NotificationPreferences,
} from '@/api/notification'
import AppNavBar from '@/components/AppNavBar.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import { useI18nStore } from '@/store/i18n'

const { t } = useI18nStore()
const userStore = useUserStore()
const info = reactive({ company_name: '', contact: '', phone: '', region: '', desc: '' })
const loadError = ref(false)
const notificationPrefs = reactive<NotificationPreferences>({
  order_enabled: true,
  device_enabled: true,
  revenue_enabled: true,
  wallet_enabled: true,
  system_enabled: true,
})
const delivery = ref<NotificationDeliveryStatus | null>(null)
const notificationLoadError = ref(false)

async function load() {
  loadError.value = false
  const [supplierResult] = await Promise.allSettled([
    request({ url: '/supplier/mine' }),
    loadNotificationSettings(),
  ])
  if (supplierResult.status === 'fulfilled') {
    const d = supplierResult.value
    if (d && (d as any).status === 'approved') {
      Object.assign(info, d)
    }
  } else {
    loadError.value = true
  }
}
onShow(() => load())

async function loadNotificationSettings() {
  notificationLoadError.value = false
  try {
    const result = await getNotificationPreferences(true)
    Object.assign(notificationPrefs, result.preferences)
    delivery.value = result.delivery
  } catch {
    notificationLoadError.value = true
  }
}

async function switchBack() {
  try { await userStore.switchRole(); uni.switchTab({ url: '/pages/profile/index' }) } catch {}
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.read-only-note { padding: 20rpx 22rpx; margin: 16rpx 0 18rpx; background: var(--primary-soft); border: 1rpx solid rgba(24,175,196,.2); border-radius: var(--radius); }
.read-only-title { display: block; color: var(--text); font-size: 24rpx; font-weight: 700; }
.read-only-desc { display: block; margin-top: 6rpx; color: var(--text-sub); font-size: 21rpx; line-height: 1.5; }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--card-border); }
.form { padding: 16rpx 32rpx; margin-bottom: 24rpx; }
.field { margin-bottom: 28rpx; }
.flabel { color: var(--text-sub); font-size: 24rpx; display: block; margin-bottom: 12rpx; }
.fvalue { display: block; color: var(--text); font-size: 28rpx; line-height: 1.45; overflow-wrap: anywhere; }
.fvalue.multiline { white-space: pre-wrap; }
.menu { padding: 0 32rpx; }
.m-item { display: flex; justify-content: space-between; align-items: center; padding: 32rpx 0; border-bottom: 1rpx solid var(--divider); color: var(--text); font-size: 28rpx; }
.m-item:last-child { border-bottom: none; }
.m-item.danger { color: var(--down); }
.preference-value { color: var(--text-sub); font-size: 24rpx; }
.notification-status { display: flex; align-items: flex-start; gap: 16rpx; padding: 22rpx 24rpx; margin-bottom: 16rpx; color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); }
.status-dot { width: 13rpx; height: 13rpx; margin-top: 9rpx; border-radius: 50%; background: var(--up); flex-shrink: 0; }
.status-copy { flex: 1; }
.status-title { display: block; color: var(--text); font-size: 25rpx; font-weight: 700; }
.status-desc { display: block; color: var(--text-sub); font-size: 20rpx; line-height: 1.5; margin-top: 5rpx; }
.notification-error { min-height: 92rpx; display: flex; align-items: center; justify-content: space-between; gap: 20rpx; color: var(--text-sub); font-size: 22rpx; }
.load-error { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; padding: 20rpx 24rpx; margin: 24rpx 0 0; color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); font-size: 23rpx; line-height: 1.5; }
.load-retry { flex-shrink: 0; color: var(--primary); font-weight: 700; min-height: 64rpx; display: flex; align-items: center; }
</style>
