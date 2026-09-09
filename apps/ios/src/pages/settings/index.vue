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
        <view class="menu-item" @tap="onRecoveryEmail">
          <view class="mi-left">
            <AppIcon name="verified" :size="40" />
            <view>
              <text class="mi-text">{{ t('recoveryEmail') }}</text>
              <text class="binding-hint">{{ t(recoveryEmailHintKey) }}</text>
            </view>
          </view>
          <view class="mi-right">
            <text class="mi-sub" :class="{ bound: recoveryEmail?.verified && !recoveryEmailLoadFailed }">{{ t(recoveryEmailStatusKey) }}</text>
            <AppIcon name="chevron" :size="36" />
          </view>
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
        <view class="menu-item" :class="{ disabled: updateChecking }" @tap="onCheckUpdate">
          <view class="mi-left">
            <AppIcon name="refresh" :size="40" />
            <text class="mi-text">{{ t(updateChecking ? 'appUpdateChecking' : 'appUpdateCheck') }}</text>
          </view>
          <view class="mi-right">
            <text class="mi-sub">v{{ appVersion }}</text>
            <AppIcon name="chevron" :size="36" />
          </view>
        </view>
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

      <SectionHeader :title="t('kaiIdentityBinding')" />
      <view class="card menu">
        <view class="menu-item" :class="{ disabled: kaiBindingLoading }" @tap="onKaiBinding">
          <view class="mi-left">
            <AppIcon name="verified" :size="40" />
            <view>
              <text class="mi-text">{{ t('kaiIdentity') }}</text>
              <text class="binding-hint">{{ t(kaiBinding?.bound ? 'kaiIdentityBoundHint' : 'kaiIdentityUnboundHint') }}</text>
            </view>
          </view>
          <view class="mi-right">
            <text class="mi-sub" :class="{ bound: kaiBinding?.bound }">{{ t(kaiBindingLoading ? 'loading' : kaiBinding?.bound ? 'kaiIdentityBound' : 'kaiIdentityUnbound') }}</text>
            <AppIcon v-if="!kaiBinding?.bound" name="chevron" :size="36" />
          </view>
        </view>
      </view>

      <SectionHeader :title="t('k_7116e7ec')" />
      <view class="card menu">
        <view class="menu-item contact-link" role="button" @tap="callContactPhone">
          <text class="mi-text">{{ t('platformContactLink', { phone: t('platformContactNumber') }) }}</text>
          <AppIcon name="chevron" :size="36" />
        </view>
        <view class="menu-item" @tap="nav('/pages/account-deletion/index')">
          <view class="mi-left">
            <AppIcon name="shield" :size="40" />
            <text class="mi-text">{{ t('accountDeletion') }}</text>
          </view>
          <AppIcon name="chevron" :size="36" />
        </view>
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
import { computed, onUnmounted, ref } from 'vue'
import { onHide, onShow } from '@dcloudio/uni-app'
import { useUserStore } from '@/store/user'
import {
  getKaiBindingStatus,
  getRecoveryEmailStatus,
  startKaiBinding,
  type KaiBindingStatus,
  type RecoveryEmailStatus,
} from '@/api/user'
import AppNavBar from '@/components/AppNavBar.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import ConfirmSheet from '@/components/ConfirmSheet.vue'
import AppIcon from '@/components/AppIcon.vue'
import { callContactPhone } from '@/utils/contact-phone'
import { navigateTo as nav } from '@/utils/nav'
import { useI18nStore } from '@/store/i18n'
import { useThemeStore, type ThemeMode } from '@/store/theme'
import { useNotificationStore } from '@/store/notification'
import { checkForAppUpdate, getInstalledAppVersion } from '@/utils/app-update'

const i18n = useI18nStore()
const { t } = i18n
const userStore = useUserStore()
const themeStore = useThemeStore()
const notificationStore = useNotificationStore()
const showLogout = ref(false)
const kaiBinding = ref<KaiBindingStatus | null>(null)
const kaiBindingLoading = ref(false)
const updateChecking = ref(false)
const recoveryEmail = ref<RecoveryEmailStatus | null>(null)
const recoveryEmailLoading = ref(false)
const recoveryEmailLoadFailed = ref(false)
let recoveryEmailActive = false
let recoveryEmailGeneration = 0
const themeOptions: Array<{ mode: ThemeMode; key: string }> = [
  { mode: 'system', key: 'themeSystem' },
  { mode: 'light', key: 'themeLight' },
  { mode: 'dark', key: 'themeDark' },
]
const themeLabel = computed(() => t(themeOptions.find((item) => item.mode === themeStore.mode)?.key || 'themeSystem'))
const notificationSummary = computed(() => notificationStore.unread > 0
  ? t('unreadNotificationCount', { count: notificationStore.unread })
  : t('inAppNotificationsEnabledShort'))
const recoveryEmailHintKey = computed(() => recoveryEmailLoadFailed.value
  ? 'recoveryEmailLoadFailed'
  : recoveryEmail.value?.verified ? 'recoveryEmailBoundHint' : 'recoveryEmailUnboundHint')
const recoveryEmailStatusKey = computed(() => {
  if (recoveryEmailLoading.value) return 'loading'
  if (recoveryEmailLoadFailed.value) return 'recoveryEmailStatusUnavailable'
  return recoveryEmail.value?.verified ? 'recoveryEmailBound' : 'recoveryEmailUnbound'
})
const appVersion = getInstalledAppVersion().name

function onNotify() {
  nav('/pages/notifications/index')
}
async function refreshKaiBinding() {
  if (!userStore.isLogin || kaiBindingLoading.value) return
  kaiBindingLoading.value = true
  try {
    kaiBinding.value = await getKaiBindingStatus(true)
  } catch {
    kaiBinding.value = null
  } finally {
    kaiBindingLoading.value = false
  }
}
async function refreshRecoveryEmail() {
  if (!recoveryEmailActive || !userStore.isLogin) return
  const generation = ++recoveryEmailGeneration
  const sessionToken = userStore.token
  const sessionUserId = userStore.userInfo?.id ?? null
  recoveryEmailLoading.value = true
  recoveryEmailLoadFailed.value = false
  const isCurrentRequest = () => recoveryEmailActive
    && generation === recoveryEmailGeneration
    && userStore.isLogin
    && userStore.token === sessionToken
    && (sessionUserId === null || (userStore.userInfo?.id ?? null) === sessionUserId)
  try {
    const nextStatus = await getRecoveryEmailStatus(true)
    if (!isCurrentRequest()) return
    recoveryEmail.value = nextStatus
  } catch {
    if (!isCurrentRequest()) return
    recoveryEmail.value = null
    recoveryEmailLoadFailed.value = true
  } finally {
    if (isCurrentRequest()) recoveryEmailLoading.value = false
  }
}
onShow(() => {
  recoveryEmailActive = true
  notificationStore.refresh(true).catch(() => {})
  void refreshKaiBinding()
  void refreshRecoveryEmail()
})
function deactivateRecoveryEmail() {
  recoveryEmailActive = false
  recoveryEmailGeneration += 1
  recoveryEmail.value = null
  recoveryEmailLoading.value = false
  recoveryEmailLoadFailed.value = false
}
onHide(deactivateRecoveryEmail)
function openKaiAuthorization(url: string) {
  // #ifdef H5
  window.location.assign(url)
  // #endif
  // #ifdef APP-PLUS
  plus.runtime.openURL(url)
  // #endif
}
async function beginKaiBinding() {
  if (kaiBindingLoading.value || kaiBinding.value?.bound) return
  kaiBindingLoading.value = true
  try {
    const result = await startKaiBinding()
    openKaiAuthorization(result.authorization_url)
  } finally {
    kaiBindingLoading.value = false
  }
}
function onKaiBinding() {
  if (kaiBinding.value?.bound || kaiBindingLoading.value) return
  uni.showModal({
    title: t('kaiIdentityBinding'),
    content: t('kaiIdentityBindingConfirm'),
    confirmText: t('confirm'),
    success: ({ confirm }) => { if (confirm) void beginKaiBinding() },
  })
}
function onKaiBindingChanged() {
  void refreshKaiBinding()
}
function onSessionChanged() {
  recoveryEmailGeneration += 1
  recoveryEmail.value = null
  recoveryEmailLoading.value = false
  recoveryEmailLoadFailed.value = false
  if (recoveryEmailActive) void refreshRecoveryEmail()
}
uni.$on('wod-kai-binding-changed', onKaiBindingChanged)
uni.$on('wod-session-changed', onSessionChanged)
onUnmounted(() => {
  deactivateRecoveryEmail()
  uni.$off('wod-kai-binding-changed', onKaiBindingChanged)
  uni.$off('wod-session-changed', onSessionChanged)
})
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
function onRecoveryEmail() {
  nav('/pages/recovery-email/index')
}
function onHelp() {
  uni.showModal({
    title: t('k_e885e3f4'),
    content: t('closedTestSupportNotice'),
    showCancel: false,
    confirmText: t('知道了'),
  })
}
async function onCheckUpdate() {
  if (updateChecking.value) return
  updateChecking.value = true
  try {
    await checkForAppUpdate('ios', { manual: true })
  } finally {
    updateChecking.value = false
  }
}
function onAbout() {
  uni.showModal({
    title: t('k_17651c8f'),
    content: `ZTW - ${t('算力资源撮合平台')}\n${i18n.lang === 'en' ? 'Version' : '版本'} v${appVersion}`,
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
.menu-item.disabled { opacity: .55; }
.mi-left { display: flex; align-items: center; gap: 20rpx; }
.mi-text { color: var(--text); font-size: 30rpx; }
.mi-text.d-text { color: var(--down); }
.mi-right { display: flex; align-items: center; gap: 8rpx; }
.mi-sub { color: var(--text-dim); font-size: 26rpx; }
.mi-sub.bound { color: var(--up); }
.contact-link .mi-text { color: var(--primary); }
.binding-hint { display: block; max-width: 430rpx; margin-top: 5rpx; color: var(--text-sub); font-size: 20rpx; line-height: 1.45; }
.settings-badge { min-width: 30rpx; height: 30rpx; padding: 0 7rpx; display: flex; align-items: center; justify-content: center; box-sizing: border-box; border-radius: 15rpx; color: #fff; background: var(--down); font-size: 17rpx; font-weight: 700; }
.theme-value { color: var(--text-sub); }
</style>
