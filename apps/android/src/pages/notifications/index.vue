<template>
  <view :class="['page', pageMotionClass]">
    <AppNavBar :title="t('notificationCenter')">
      <template #right>
        <text v-if="notificationStore.unread > 0" class="mark-all" @tap="onMarkAll">{{ t('markAllRead') }}</text>
      </template>
    </AppNavBar>

    <view class="shell">
      <view class="delivery-card" :class="{ pending: delivery && !delivery.system_push_configured }">
        <view class="delivery-dot"></view>
        <view class="delivery-copy">
          <text class="delivery-title">{{ t('inAppNotificationsEnabled') }}</text>
          <text class="delivery-desc">
            {{ delivery?.system_push_configured ? t('systemPushConfigured') : t('systemPushPending') }}
          </text>
        </view>
      </view>

      <view class="preference-card card">
        <view class="section-title-row">
          <text class="section-title">{{ t('notificationPreferences') }}</text>
          <text v-if="preferencesLoading" class="section-status">{{ t('loading') }}</text>
        </view>
        <view v-if="preferenceError" class="inline-error">
          <text>{{ t('notificationPreferencesLoadFailed') }}</text>
          <text class="inline-retry" @tap="loadPreferences">{{ t('retry') }}</text>
        </view>
        <template v-else-if="preferences">
          <view v-for="option in preferenceOptions" :key="option.key" class="preference-row">
            <view>
              <text class="preference-name">{{ t(option.label) }}</text>
              <text class="preference-desc">{{ t(option.desc) }}</text>
            </view>
            <switch
              color="#18AFC4"
              :checked="preferences[option.key]"
              :disabled="savingPreference === option.key"
              @change="onPreferenceChange(option.key, $event)"
            />
          </view>
        </template>
      </view>

      <scroll-view scroll-x class="filter-scroll" :show-scrollbar="false">
        <view class="filters">
          <view
            v-for="filter in filters"
            :key="filter.value || 'all'"
            class="filter-chip pressable"
            :class="{ active: activeType === filter.value }"
            @tap="selectType(filter.value)"
          >{{ t(filter.label) }}</view>
        </view>
      </scroll-view>

      <view v-if="loading && !items.length" class="state">{{ t('loading') }}</view>
      <view v-else-if="loadError && !items.length" class="state error-state">
        <text>{{ t('notificationsLoadFailed') }}</text>
        <view class="retry-button" role="button" @tap="load(true)">{{ t('retry') }}</view>
      </view>
      <view v-else-if="!items.length" class="card empty-card">
        <EmptyState :text="t('noNotifications')" />
      </view>

      <view
        v-for="notification in items"
        :key="notification.id"
        class="card notification-row pressable"
        :class="{ unread: !notification.is_read }"
        @tap="onTap(notification)"
      >
        <view class="type-column">
          <view class="type-mark" :class="notification.type"></view>
          <view v-if="!notification.is_read" class="unread-dot"></view>
        </view>
        <view class="notification-copy">
          <view class="notification-head">
            <text class="notification-title">{{ localizedTitle(notification) }}</text>
            <text class="notification-type">{{ t(typeLabel(notification.type)) }}</text>
          </view>
          <text v-if="localizedContent(notification)" class="notification-content">{{ localizedContent(notification) }}</text>
          <text class="notification-date">{{ formatDate(notification.created_at) }}</text>
        </view>
        <text v-if="notification.action_url" class="row-chevron">›</text>
      </view>

      <view v-if="loadingMore" class="footer-state">{{ t('loading') }}</view>
      <view v-else-if="loadError && items.length" class="footer-state footer-error" @tap="load(false)">
        {{ t('loadMoreFailedRetry') }}
      </view>
      <view v-else-if="items.length && !hasMore" class="footer-state">{{ t('noMoreNotifications') }}</view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onPullDownRefresh, onReachBottom, onShow } from '@dcloudio/uni-app'
import {
  getNotificationPreferences,
  getNotifications,
  markAllRead,
  markRead,
  updateNotificationPreferences,
  type NotificationDeliveryStatus,
  type NotificationItem,
  type NotificationPreferences,
  type NotificationType,
} from '@/api/notification'
import { formatDate } from '@/utils/format'
import { navigateTo } from '@/utils/nav'
import { useNotificationStore } from '@/store/notification'
import AppNavBar from '@/components/AppNavBar.vue'
import EmptyState from '@/components/EmptyState.vue'
import { useI18nStore } from '@/store/i18n'
import { usePageMotion } from '@/utils/page-motion'

type PreferenceKey = keyof Pick<NotificationPreferences,
  'order_enabled' | 'device_enabled' | 'revenue_enabled' | 'wallet_enabled' | 'system_enabled'>

const i18n = useI18nStore()
const { t, tr } = i18n
const { pageMotionClass } = usePageMotion()
const notificationStore = useNotificationStore()
const items = ref<NotificationItem[]>([])
const loading = ref(true)
const loadingMore = ref(false)
const loadError = ref(false)
const page = ref(1)
const hasMore = ref(false)
const activeType = ref<NotificationType | undefined>()
const preferences = ref<NotificationPreferences | null>(null)
const delivery = ref<NotificationDeliveryStatus | null>(null)
const preferencesLoading = ref(true)
const preferenceError = ref(false)
const savingPreference = ref<PreferenceKey | null>(null)
let loadGeneration = 0

const filters: Array<{ value?: NotificationType; label: string }> = [
  { label: 'allNotifications' },
  { value: 'order', label: 'orderNotifications' },
  { value: 'device', label: 'deviceAlerts' },
  { value: 'revenue', label: 'revenueReminders' },
  { value: 'wallet', label: 'walletNotifications' },
  { value: 'system', label: 'systemNotifications' },
]

const preferenceOptions: Array<{ key: PreferenceKey; label: string; desc: string }> = [
  { key: 'order_enabled', label: 'orderNotifications', desc: 'orderNotificationsDesc' },
  { key: 'device_enabled', label: 'deviceAlerts', desc: 'deviceAlertsDesc' },
  { key: 'revenue_enabled', label: 'revenueReminders', desc: 'revenueRemindersDesc' },
  { key: 'wallet_enabled', label: 'walletNotifications', desc: 'walletNotificationsDesc' },
  { key: 'system_enabled', label: 'systemNotifications', desc: 'systemNotificationsDesc' },
]

async function load(reset = true) {
  if (!reset && (!hasMore.value || loadingMore.value || loading.value)) return
  const generation = ++loadGeneration
  if (reset) {
    loading.value = true
    page.value = 1
  } else {
    loadingMore.value = true
  }
  loadError.value = false
  const targetPage = reset ? 1 : page.value + 1
  try {
    const result = await getNotifications({
      page: targetPage,
      page_size: 20,
      type_filter: activeType.value,
    }, true)
    if (generation !== loadGeneration) return
    items.value = reset ? result.items : [...items.value, ...result.items]
    page.value = result.page
    hasMore.value = result.has_more
    notificationStore.setUnread(result.unread)
  } catch {
    if (generation === loadGeneration) loadError.value = true
  } finally {
    if (generation === loadGeneration) {
      loading.value = false
      loadingMore.value = false
    }
  }
}

async function loadPreferences() {
  preferencesLoading.value = true
  preferenceError.value = false
  try {
    const result = await getNotificationPreferences(true)
    preferences.value = result.preferences
    delivery.value = result.delivery
  } catch {
    preferenceError.value = true
  } finally {
    preferencesLoading.value = false
  }
}

onShow(() => {
  Promise.all([load(true), loadPreferences()]).catch(() => {})
})

onPullDownRefresh(async () => {
  await Promise.allSettled([load(true), loadPreferences()])
  uni.stopPullDownRefresh()
})

onReachBottom(() => load(false))

function selectType(type?: NotificationType) {
  if (activeType.value === type) return
  activeType.value = type
  load(true).catch(() => {})
}

function localizedTitle(notification: NotificationItem) {
  if (i18n.lang === 'en' && notification.title_en) return notification.title_en
  return tr(notification.title)
}

function localizedContent(notification: NotificationItem) {
  if (i18n.lang === 'en' && notification.content_en) return notification.content_en
  return tr(notification.content || '')
}

function typeLabel(type: string) {
  return ({
    order: 'orderNotifications',
    device: 'deviceAlerts',
    revenue: 'revenueReminders',
    wallet: 'walletNotifications',
    system: 'systemNotifications',
  } as Record<string, string>)[type] || 'systemNotifications'
}

async function onTap(notification: NotificationItem) {
  if (!notification.is_read) {
    try {
      await markRead(notification.id)
      notification.is_read = true
      notificationStore.setUnread(notificationStore.unread - 1)
    } catch {
      return
    }
  }
  if (notification.action_url?.startsWith('/pages/')) navigateTo(notification.action_url)
}

async function onMarkAll() {
  try {
    await markAllRead()
    items.value.forEach((item) => { item.is_read = true })
    notificationStore.setUnread(0)
    uni.showToast({ title: t('markedAllRead'), icon: 'success' })
  } catch { /* request already provides the failure message */ }
}

async function onPreferenceChange(key: PreferenceKey, event: any) {
  if (!preferences.value || savingPreference.value) return
  const previous = preferences.value[key]
  preferences.value[key] = Boolean(event.detail.value)
  savingPreference.value = key
  try {
    const result = await updateNotificationPreferences({ [key]: preferences.value[key] })
    preferences.value = result.preferences
    delivery.value = result.delivery
    uni.showToast({ title: t('saved'), icon: 'success' })
  } catch {
    if (preferences.value) preferences.value[key] = previous
  } finally {
    savingPreference.value = null
  }
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.mark-all { min-height: 72rpx; display: flex; align-items: center; color: var(--primary); font-size: 24rpx; }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--border); }
.delivery-card { display: flex; align-items: flex-start; gap: 18rpx; padding: 24rpx 28rpx; margin-bottom: 20rpx; border: 1rpx solid rgba(22, 163, 74, 0.20); border-radius: var(--radius); background: var(--up-soft); }
.delivery-card.pending { border-color: var(--border); background: var(--bg-2); }
.delivery-dot { width: 14rpx; height: 14rpx; margin-top: 10rpx; border-radius: 50%; background: var(--up); flex-shrink: 0; }
.delivery-card.pending .delivery-dot { background: #D97706; }
.delivery-copy { flex: 1; }
.delivery-title { display: block; color: var(--text); font-size: 26rpx; font-weight: 700; }
.delivery-desc { display: block; color: var(--text-sub); font-size: 22rpx; line-height: 1.5; margin-top: 6rpx; }
.preference-card { padding: 12rpx 28rpx; margin-bottom: 20rpx; }
.section-title-row { min-height: 76rpx; display: flex; align-items: center; justify-content: space-between; }
.section-title { color: var(--text); font-size: 27rpx; font-weight: 700; }
.section-status { color: var(--text-dim); font-size: 21rpx; }
.preference-row { min-height: 104rpx; display: flex; align-items: center; justify-content: space-between; gap: 24rpx; border-top: 1rpx solid var(--divider); }
.preference-row > view { flex: 1; min-width: 0; }
.preference-name { display: block; color: var(--text); font-size: 25rpx; }
.preference-desc { display: block; color: var(--text-sub); font-size: 20rpx; line-height: 1.4; margin-top: 5rpx; }
.inline-error { min-height: 80rpx; display: flex; align-items: center; justify-content: space-between; gap: 20rpx; color: var(--text-sub); font-size: 22rpx; border-top: 1rpx solid var(--divider); }
.inline-retry { color: var(--primary); font-weight: 700; }
.filter-scroll { white-space: nowrap; margin-bottom: 20rpx; }
.filters { display: inline-flex; gap: 12rpx; padding-right: 20rpx; }
.filter-chip { min-height: 64rpx; padding: 0 24rpx; display: flex; align-items: center; justify-content: center; border: 1rpx solid var(--border); border-radius: 32rpx; color: var(--text-sub); background: var(--card); font-size: 22rpx; }
.filter-chip.active { color: var(--primary); border-color: var(--primary); background: var(--primary-soft); font-weight: 700; }
.state { color: var(--text-sub); text-align: center; padding: 60rpx 0; font-size: 26rpx; }
.error-state { display: flex; flex-direction: column; align-items: center; gap: 18rpx; }
.retry-button { min-height: 68rpx; padding: 0 28rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: var(--radius); font-weight: 700; }
.empty-card { padding: 60rpx 0; }
.notification-row { display: flex; align-items: flex-start; gap: 16rpx; padding: 28rpx 24rpx; margin-bottom: 16rpx; }
.notification-row.unread { background: var(--primary-soft); border-color: rgba(24, 175, 196, 0.24); }
.type-column { width: 24rpx; padding-top: 8rpx; display: flex; flex-direction: column; align-items: center; gap: 14rpx; flex-shrink: 0; }
.type-mark { width: 8rpx; height: 36rpx; border-radius: 4rpx; background: var(--text-dim); }
.type-mark.order { background: var(--primary); }
.type-mark.device { background: #D97706; }
.type-mark.revenue { background: var(--up); }
.type-mark.wallet { background: #2563EB; }
.unread-dot { width: 12rpx; height: 12rpx; border-radius: 50%; background: var(--primary); }
.notification-copy { flex: 1; min-width: 0; }
.notification-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16rpx; }
.notification-title { color: var(--text); font-size: 28rpx; font-weight: 700; line-height: 1.4; }
.notification-type { flex-shrink: 0; color: var(--text-sub); font-size: 19rpx; padding: 5rpx 10rpx; background: var(--bg-2); border-radius: 8rpx; }
.notification-content { color: var(--text-sub); font-size: 24rpx; margin-top: 10rpx; display: block; line-height: 1.55; }
.notification-date { color: var(--text-dim); font-size: 20rpx; margin-top: 12rpx; display: block; }
.row-chevron { align-self: center; color: var(--text-dim); font-size: 36rpx; }
.footer-state { padding: 28rpx 0 16rpx; color: var(--text-dim); font-size: 22rpx; text-align: center; }
.footer-error { color: var(--primary); }
</style>
