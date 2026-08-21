<template>
  <view class="page">
    <AppNavBar :title="t('k_0aeca07a')" />
    <view class="shell">
      <view v-if="loadError" class="load-error">
        <text>{{ t('supplierLoadFailedDesc') }}</text>
        <text class="load-retry" @tap="load">{{ t('retry') }}</text>
      </view>
      <SectionHeader :title="t('k_07ec72a7')" />
      <view class="card form">
        <view class="field"><text class="flabel">{{ t('k_f47e2736') }}</text><input class="finput" v-model="info.company_name" :placeholder="t('k_f47e2736')" placeholder-class="ph" /></view>
        <view class="field"><text class="flabel">{{ t('k_52409da5') }}</text><input class="finput" v-model="info.contact" :placeholder="t('k_52409da5')" placeholder-class="ph" /></view>
        <view class="field"><text class="flabel">{{ t('k_09a1f698') }}</text><input class="finput" v-model="info.phone" :placeholder="t('k_09a1f698')" placeholder-class="ph" /></view>
        <view class="field"><text class="flabel">{{ t('k_65d3ab77') }}</text><input class="finput" v-model="info.region" :placeholder="t('region')" placeholder-class="ph" /></view>
        <view class="field"><text class="flabel">{{ t('k_a784c811') }}</text><textarea class="tarea" v-model="info.desc" :placeholder="t('k_a784c811')" placeholder-class="ph" maxlength="200" /></view>
      </view>
      <view class="btn-primary" @tap="onSave">{{ t("save") }}</view>

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
            <switch color="#18AFC4" :checked="notificationPrefs.order_enabled" :disabled="notificationSaving === 'order_enabled'" @change="onNotificationToggle('order_enabled', $event)" />
          </view>
          <view class="m-item">
            <text>{{ t('k_01e08c5a') }}</text>
            <switch color="#18AFC4" :checked="notificationPrefs.device_enabled" :disabled="notificationSaving === 'device_enabled'" @change="onNotificationToggle('device_enabled', $event)" />
          </view>
          <view class="m-item">
            <text>{{ t('k_f2c846ec') }}</text>
            <switch color="#18AFC4" :checked="notificationPrefs.revenue_enabled" :disabled="notificationSaving === 'revenue_enabled'" @change="onNotificationToggle('revenue_enabled', $event)" />
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
  updateNotificationPreferences,
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
type SupplierNotificationKey = 'order_enabled' | 'device_enabled' | 'revenue_enabled'
const notificationPrefs = reactive<NotificationPreferences>({
  order_enabled: true,
  device_enabled: true,
  revenue_enabled: true,
  wallet_enabled: true,
  system_enabled: true,
})
const delivery = ref<NotificationDeliveryStatus | null>(null)
const notificationLoadError = ref(false)
const notificationSaving = ref<SupplierNotificationKey | null>(null)

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

async function onSave() {
  try {
    await request({ url: '/supplier/profile', method: 'PUT', data: { ...info } })
    uni.showToast({ title: t('已保存'), icon: 'success' })
  } catch {}
}

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

async function onNotificationToggle(key: SupplierNotificationKey, event: any) {
  if (notificationSaving.value) return
  const previous = notificationPrefs[key]
  notificationPrefs[key] = Boolean(event.detail.value)
  notificationSaving.value = key
  try {
    const result = await updateNotificationPreferences({ [key]: notificationPrefs[key] })
    Object.assign(notificationPrefs, result.preferences)
    delivery.value = result.delivery
    uni.showToast({ title: t('saved'), icon: 'success' })
  } catch {
    notificationPrefs[key] = previous
  } finally {
    notificationSaving.value = null
  }
}

async function switchBack() {
  try { await userStore.switchRole(); uni.switchTab({ url: '/pages/profile/index' }) } catch {}
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--card-border); }
.form { padding: 16rpx 32rpx; margin-bottom: 24rpx; }
.field { margin-bottom: 28rpx; }
.flabel { color: var(--text-sub); font-size: 24rpx; display: block; margin-bottom: 12rpx; }
.finput { color: var(--text); font-size: 30rpx; }
.tarea { width: 100%; min-height: 120rpx; color: var(--text); font-size: 28rpx; line-height: 1.5; }
.ph { color: var(--text-dim); }
.btn-primary { background: linear-gradient(135deg, var(--primary), var(--primary)); color: #fff; text-align: center; padding: 28rpx 0; border-radius: var(--radius); font-size: 30rpx; font-weight: 600; margin-bottom: 24rpx; }
.menu { padding: 0 32rpx; }
.m-item { display: flex; justify-content: space-between; align-items: center; padding: 32rpx 0; border-bottom: 1rpx solid var(--divider); color: var(--text); font-size: 28rpx; }
.m-item:last-child { border-bottom: none; }
.m-item.danger { color: var(--down); }
.notification-status { display: flex; align-items: flex-start; gap: 16rpx; padding: 22rpx 24rpx; margin-bottom: 16rpx; color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); }
.status-dot { width: 13rpx; height: 13rpx; margin-top: 9rpx; border-radius: 50%; background: var(--up); flex-shrink: 0; }
.status-copy { flex: 1; }
.status-title { display: block; color: var(--text); font-size: 25rpx; font-weight: 700; }
.status-desc { display: block; color: var(--text-sub); font-size: 20rpx; line-height: 1.5; margin-top: 5rpx; }
.notification-error { min-height: 92rpx; display: flex; align-items: center; justify-content: space-between; gap: 20rpx; color: var(--text-sub); font-size: 22rpx; }
.load-error { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; padding: 20rpx 24rpx; margin: 24rpx 0 0; color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); font-size: 23rpx; line-height: 1.5; }
.load-retry { flex-shrink: 0; color: var(--primary); font-weight: 700; min-height: 64rpx; display: flex; align-items: center; }
</style>
