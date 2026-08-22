<template>
  <view class="page">
    <AppNavBar :title="t('settings')" />
    <scroll-view scroll-y class="body">
      <SectionHeader :title="t('k_aa05fd09')" />
      <view class="card menu">
        <view class="menu-item" @tap="onTheme">
          <view class="mi-left">
            <AppIcon name="settings" :size="40" />
            <text class="mi-text">{{ t('appearance') }}</text>
          </view>
          <view class="mi-right">
            <text class="mi-sub theme-value">{{ themeLabel }}</text>
            <AppIcon name="chevron" :size="36" />
          </view>
        </view>
        <view class="menu-item" @tap="onNotify">
          <view class="mi-left">
            <AppIcon name="bell" :size="40" />
            <text class="mi-text">{{ t('k_d1d4c33c') }}</text>
          </view>
          <view class="mi-right">
            <text class="mi-sub">{{ notificationSummary }}</text>
            <text v-if="notificationStore.unread > 0" class="settings-badge">{{ notificationStore.unread > 99 ? '99+' : notificationStore.unread }}</text>
            <AppIcon name="chevron" :size="36" />
          </view>
        </view>
        <view class="menu-item" @tap="onPassword">
          <view class="mi-left">
            <AppIcon name="shield" :size="40" />
            <text class="mi-text">{{ t('k_7fc88aee') }}</text>
          </view>
          <AppIcon name="chevron" :size="36" />
        </view>
        <view class="menu-item" @tap="onHelp">
          <view class="mi-left">
            <AppIcon name="help" :size="40" />
            <text class="mi-text">{{ t('k_e885e3f4') }}</text>
          </view>
          <AppIcon name="chevron" :size="36" />
        </view>
      </view>

      <SectionHeader :title="t('k_81d9f505')" />
      <view class="card menu">
        <view class="menu-item" @tap="onAbout">
          <view class="mi-left">
            <AppIcon name="shield" :size="40" />
            <text class="mi-text">{{ t('k_17651c8f') }}</text>
          </view>
          <view class="mi-right">
            <text class="mi-sub">v{{ appVersion }}</text>
            <AppIcon name="chevron" :size="36" />
          </view>
        </view>
      </view>

      <SectionHeader :title="t('k_7116e7ec')" />
      <view class="card menu">
        <view class="menu-item danger" @tap="showLogout = true">
          <view class="mi-left">
            <AppIcon name="logout" :size="40" />
            <text class="mi-text d-text">{{ t('k_44efd179') }}</text>
          </view>
        </view>
      </view>
    </scroll-view>

    <ConfirmSheet
      :visible="showLogout"
      :title="t('k_44efd179')"
      :desc="t('k_4ec210a8')"
      :cancelText="t('cancel')"
      :confirmText="t('k_c3992269')"
      @cancel="showLogout = false"
      @confirm="onLogout"
    />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { useUserStore } from '@/store/user'
import AppNavBar from '@/components/AppNavBar.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import ConfirmSheet from '@/components/ConfirmSheet.vue'
import AppIcon from '@/components/AppIcon.vue'
import { navigateTo as nav } from '@/utils/nav'
import { useI18nStore } from '@/store/i18n'
import { useThemeStore, type ThemeMode } from '@/store/theme'
import { useNotificationStore } from '@/store/notification'

const i18n = useI18nStore()
const { t } = i18n
const userStore = useUserStore()
const themeStore = useThemeStore()
const notificationStore = useNotificationStore()
const showLogout = ref(false)
const themeOptions: Array<{ mode: ThemeMode; key: string }> = [
  { mode: 'system', key: 'themeSystem' },
  { mode: 'light', key: 'themeLight' },
  { mode: 'dark', key: 'themeDark' },
]
const themeLabel = computed(() => t(themeOptions.find((item) => item.mode === themeStore.mode)?.key || 'themeSystem'))
const notificationSummary = computed(() => notificationStore.unread > 0
  ? t('unreadNotificationCount', { count: notificationStore.unread })
  : t('inAppNotificationsEnabledShort'))
const appVersion = (() => {
  try {
    return uni.getAppBaseInfo().appVersion || '1.0.3'
  } catch {
    return '1.0.3'
  }
})()

function onNotify() {
  nav('/pages/notifications/index')
}
onShow(() => notificationStore.refresh(true).catch(() => {}))
function onTheme() {
  uni.showActionSheet({
    title: t('chooseTheme'),
    itemList: themeOptions.map((item) => {
      const label = t(item.key)
      return item.mode === themeStore.mode ? `✓ ${label}` : label
    }),
    success: ({ tapIndex }) => {
      const selected = themeOptions[tapIndex]
      if (selected) themeStore.setMode(selected.mode)
    },
  })
}
function onPassword() {
  nav('/pages/password/index')
}
function onHelp() {
  uni.showModal({
    title: t('k_e885e3f4'),
    content: t('closedTestSupportNotice'),
    showCancel: false,
    confirmText: t('知道了'),
  })
}
function onAbout() {
  uni.showModal({
    title: t('k_17651c8f'),
    content: `北斗 kai - ${t('AI 算力资产管理')}\n${i18n.lang === 'en' ? 'Version' : '版本'} v${appVersion}`,
    showCancel: false,
    confirmText: t('知道了'),
  })
}

function onLogout() {
  showLogout.value = false
  userStore.logout()
  uni.reLaunch({ url: '/pages/login/index' })
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.body { flex: 1; padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.card { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }

.menu { padding: 0 32rpx; }
.menu-item { display: flex; align-items: center; justify-content: space-between; padding: 32rpx 0; border-bottom: 1rpx solid var(--divider); color: var(--text-sub); }
.menu-item:last-child { border-bottom: none; }
.menu-item.danger { color: var(--down); }
.mi-left { display: flex; align-items: center; gap: 20rpx; }
.mi-text { color: var(--text); font-size: 30rpx; }
.mi-text.d-text { color: var(--down); }
.mi-right { display: flex; align-items: center; gap: 8rpx; }
.mi-sub { color: var(--text-dim); font-size: 26rpx; }
.settings-badge { min-width: 30rpx; height: 30rpx; padding: 0 7rpx; display: flex; align-items: center; justify-content: center; box-sizing: border-box; border-radius: 15rpx; color: #fff; background: var(--down); font-size: 17rpx; font-weight: 700; }
.theme-value { color: var(--text-sub); }
</style>
