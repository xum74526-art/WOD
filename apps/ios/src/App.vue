<script setup lang="ts">
import { onHide, onLaunch, onShow } from '@dcloudio/uni-app'
import { useUserStore } from './store/user'
import { useThemeStore } from './store/theme'
import { useI18nStore } from './store/i18n'
import { useHostingStore } from './store/hosting'
import { useNotificationStore } from './store/notification'
import { useCommerceStore } from './store/commerce'
import { kaiAuthCallbackFingerprint, parseKaiAuthUrl } from './utils/kai-auth-callback'
import { stageDeletionKaiCallback } from './utils/account-deletion-kai-callback'
import {
  hasPendingLoginKaiCallback,
  PENDING_KAI_INTENT_KEY,
  readPendingKaiLoginIntent,
  stageLoginKaiCallback,
} from './utils/login-kai-callback'
import { stagePasswordResetCallback } from './utils/password-reset-callback'
import { checkForAppUpdate } from './utils/app-update'
import { CLIENT_PLATFORM } from './utils/client-platform'
import {
  hasCurrentPrivacyConsent,
  PRIVACY_CONSENT_EVENT,
  PRIVACY_CONSENT_REVOKED_EVENT,
} from './utils/privacy-consent'

const HANDLED_KAI_BIND_CALLBACK_KEY = 'wod_kai_bind_callback_fingerprint'
let kaiBindingCallbackProcessing = ''
let kaiBindingProbeTimer: ReturnType<typeof setTimeout> | null = null
let passwordResetNavigationTimer: ReturnType<typeof setTimeout> | null = null
let appUpdateTimer: ReturnType<typeof setTimeout> | null = null
let loginKaiCallbackNavigationTimer: ReturnType<typeof setTimeout> | null = null
let networkRuntimeStarted = false

function currentRoute() {
  const pages = getCurrentPages()
  return pages[pages.length - 1]?.route || ''
}

function ensurePrivacyConsentPage() {
  const route = currentRoute()
  if (route === 'pages/privacy-consent/index' || route === 'pages/agreement/index') return
  uni.reLaunch({ url: '/pages/privacy-consent/index' })
}

function runtimeArguments() {
  // #ifdef APP-PLUS
  return plus.runtime.arguments
  // #endif
  return ''
}

function runtimeKaiCallback() {
  return parseKaiAuthUrl(runtimeArguments())
}

function captureLoginKaiCallback() {
  const hasPendingIntent = readPendingKaiLoginIntent(
    uni.getStorageSync(PENDING_KAI_INTENT_KEY),
  ) !== null
  return stageLoginKaiCallback(runtimeArguments(), hasPendingIntent)
}

function routePendingLoginKaiCallback() {
  if (!hasCurrentPrivacyConsent() || !hasPendingLoginKaiCallback()) return false
  const route = currentRoute()
  // The local consent page owns the first navigation after acceptance. It will
  // route directly to login when a callback was captured during cold start.
  if (route === 'pages/privacy-consent/index') return true
  if (!route) {
    if (!loginKaiCallbackNavigationTimer) {
      loginKaiCallbackNavigationTimer = setTimeout(() => {
        loginKaiCallbackNavigationTimer = null
        routePendingLoginKaiCallback()
      }, 0)
    }
    return true
  }
  if (route === 'pages/login/index') {
    uni.$emit('wod-kai-login-callback-ready')
    return true
  }
  const url = '/pages/login/index'
  uni.navigateTo({ url, fail: () => uni.reLaunch({ url }) })
  return true
}

function handlePasswordResetCallback(allowRepeatedIntent = false) {
  if (!hasCurrentPrivacyConsent()) return false
  if (!stagePasswordResetCallback(runtimeArguments(), allowRepeatedIntent)) return false
  if (passwordResetNavigationTimer) clearTimeout(passwordResetNavigationTimer)
  passwordResetNavigationTimer = setTimeout(() => {
    passwordResetNavigationTimer = null
    if (!hasCurrentPrivacyConsent()) return
    const pages = getCurrentPages()
    const currentRoute = pages[pages.length - 1]?.route || ''
    if (currentRoute === 'pages/reset-password/index') {
      uni.$emit('wod-password-reset-token-ready')
      return
    }
    const url = '/pages/reset-password/index'
    uni.navigateTo({ url, fail: () => uni.reLaunch({ url }) })
  }, 120)
  return true
}

async function handleKaiBindingCallback() {
  if (!hasCurrentPrivacyConsent()) return false
  const callback = runtimeKaiCallback()
  if (!callback?.bindTicket) return false
  const user = useUserStore()
  if (!user.isLogin) return false
  const fingerprint = kaiAuthCallbackFingerprint(callback)
  if (fingerprint === kaiBindingCallbackProcessing) return true
  if (uni.getStorageSync(HANDLED_KAI_BIND_CALLBACK_KEY) === fingerprint) return true
  kaiBindingCallbackProcessing = fingerprint
  try {
    await user.bindKaiIdentity(callback.bindTicket)
    uni.setStorageSync(HANDLED_KAI_BIND_CALLBACK_KEY, fingerprint)
    uni.showToast({ title: useI18nStore().t('kaiBindingSucceeded'), icon: 'success' })
  } catch {
    uni.showToast({ title: useI18nStore().t('kaiBindingFailed'), icon: 'none' })
  } finally {
    kaiBindingCallbackProcessing = ''
  }
  return true
}

function handleDeletionKaiCallback() {
  if (!hasCurrentPrivacyConsent()) return false
  if (!stageDeletionKaiCallback(runtimeKaiCallback())) return false
  const route = currentRoute()
  if (route === 'pages/account-deletion/index') {
    uni.$emit('wod-deletion-kai-callback-ready')
  } else {
    const url = '/pages/account-deletion/index'
    uni.navigateTo({ url, fail: () => uni.reLaunch({ url }) })
  }
  return true
}

function probeKaiBindingCallback() {
  if (!hasCurrentPrivacyConsent()) return
  if (kaiBindingProbeTimer) clearTimeout(kaiBindingProbeTimer)
  const delays = [0, 120, 320, 700]
  const probe = (index: number) => {
    if (handleDeletionKaiCallback()) return
    captureLoginKaiCallback()
    if (routePendingLoginKaiCallback()) return
    void handleKaiBindingCallback().then((handled) => {
      if (!hasCurrentPrivacyConsent()) return
      if (handled || index + 1 >= delays.length) return
      kaiBindingProbeTimer = setTimeout(() => probe(index + 1), delays[index + 1] - delays[index])
    })
  }
  probe(0)
}

function registerKaiBindingListener() {
  // #ifdef APP-PLUS
  const globalEvent = (plus as unknown as {
    globalEvent?: { addEventListener(event: string, listener: () => void): void }
  }).globalEvent
  globalEvent?.addEventListener('newintent', () => {
    captureLoginKaiCallback()
    if (!hasCurrentPrivacyConsent()) {
      ensurePrivacyConsentPage()
      return
    }
    probeKaiBindingCallback()
    handlePasswordResetCallback(true)
  })
  // #endif
}

function startNetworkedRuntime() {
  if (networkRuntimeStarted || !hasCurrentPrivacyConsent()) return false
  networkRuntimeStarted = true
  const user = useUserStore()
  user.restore()
  // #ifdef APP-PLUS
  appUpdateTimer = setTimeout(() => {
    appUpdateTimer = null
    if (hasCurrentPrivacyConsent()) void checkForAppUpdate(CLIENT_PLATFORM)
  }, 800)
  // #endif
  void useCommerceStore().refresh(true)
  if (user.isLogin) useNotificationStore().startPolling()
  handlePasswordResetCallback()
  probeKaiBindingCallback()
  return true
}

function stopNetworkedRuntime() {
  networkRuntimeStarted = false
  if (appUpdateTimer) clearTimeout(appUpdateTimer)
  if (kaiBindingProbeTimer) clearTimeout(kaiBindingProbeTimer)
  if (passwordResetNavigationTimer) clearTimeout(passwordResetNavigationTimer)
  if (loginKaiCallbackNavigationTimer) clearTimeout(loginKaiCallbackNavigationTimer)
  appUpdateTimer = null
  kaiBindingProbeTimer = null
  passwordResetNavigationTimer = null
  loginKaiCallbackNavigationTimer = null
  useNotificationStore().reset()
}

function handlePrivacyConsentRevoked() {
  stopNetworkedRuntime()
  ensurePrivacyConsentPage()
}

onLaunch(() => {
  uni.$on('wod-session-changed', () => {
    useHostingStore().reset()
    const notifications = useNotificationStore()
    notifications.reset()
    if (hasCurrentPrivacyConsent()) notifications.startPolling()
  })
  uni.$on('wod-auth-expired', () => {
    useUserStore().clearSession()
    useHostingStore().reset()
    useNotificationStore().reset()
  })
  useThemeStore().init()
  useI18nStore().init()
  registerKaiBindingListener()
  captureLoginKaiCallback()
  uni.$on(PRIVACY_CONSENT_EVENT, startNetworkedRuntime)
  uni.$on(PRIVACY_CONSENT_REVOKED_EVENT, handlePrivacyConsentRevoked)
  if (!startNetworkedRuntime()) setTimeout(ensurePrivacyConsentPage, 0)
})
onShow(() => {
  const theme = useThemeStore()
  theme.refreshSystemTheme()
  theme.applyTheme()
  captureLoginKaiCallback()
  if (!hasCurrentPrivacyConsent()) {
    useNotificationStore().stopPolling()
    setTimeout(ensurePrivacyConsentPage, 0)
    return
  }
  startNetworkedRuntime()
  if (useUserStore().isLogin) useNotificationStore().startPolling()
  void useCommerceStore().refresh()
  handlePasswordResetCallback()
  probeKaiBindingCallback()
})
onHide(() => useNotificationStore().stopPolling())
</script>

<style lang="scss">
@import './uni.scss';
@import './styles/asset-panels.scss';

/* === CSS 变量：浅色模式 === */
:root {
  color-scheme: light;
  --bg: #FFFFFF;
  --bg-2: #F8F9FA;
  --card: #F8F9FA;
  --card-border: rgba(0, 0, 0, 0.06);
  --home-card: #F6F8F8;
  --home-card-soft: #F8FAFA;
  --home-card-border: rgba(14, 52, 60, 0.075);
  --home-card-shadow: 0 8rpx 24rpx rgba(17, 92, 103, 0.045);
  --text: #111111;
  --text-sub: #999999;
  --text-dim: #CCCCCC;
  --primary: #18AFC4;
  --primary-soft: rgba(24, 175, 196, 0.10);
  --up: #16A34A;
  --up-soft: rgba(22, 163, 74, 0.10);
  --down: #EF4444;
  --down-soft: rgba(239, 68, 68, 0.10);
  --divider: rgba(0, 0, 0, 0.06);
  --border: rgba(0, 0, 0, 0.08);
  --radius: 24rpx;
  --shadow: 0 2rpx 16rpx rgba(0, 0, 0, 0.04);
  --nav-bg: #FFFFFF;
  --tab-bg: #FFFFFF;
  --input-bg: #F8F9FA;
  --overlay-card-bg: rgba(249, 252, 253, 0.98);
  --overlay-card-text: #102128;
  --overlay-card-sub: #65747a;
  --overlay-card-muted: #7b898e;
  /* uni-app exposes the real Android/iOS status-bar height through this
     built-in variable; env() alone is usually 0 on Android WebView. */
  --safe-top: var(--status-bar-height, env(safe-area-inset-top));
  --safe-bottom: env(safe-area-inset-bottom);
}

/* === CSS 变量：深色模式 === */
:root.dark,
body.dark,
page.dark,
.dark {
  color-scheme: dark;
  --bg: #0A0E14;
  --bg-2: #11161E;
  --card: rgba(255, 255, 255, 0.06);
  --card-border: rgba(255, 255, 255, 0.08);
  --home-card: rgba(255, 255, 255, 0.07);
  --home-card-soft: #131820;
  --home-card-border: rgba(255, 255, 255, 0.10);
  --home-card-shadow: 0 8rpx 26rpx rgba(0, 0, 0, 0.26);
  --text: #E8EDF2;
  --text-sub: #6B7785;
  --text-dim: #3A4452;
  --primary: #00D4FF;
  --primary-soft: rgba(0, 212, 255, 0.12);
  --up: #00FF88;
  --up-soft: rgba(0, 255, 136, 0.10);
  --down: #FF3B3B;
  --down-soft: rgba(255, 59, 59, 0.10);
  --divider: rgba(255, 255, 255, 0.06);
  --border: rgba(255, 255, 255, 0.08);
  --shadow: 0 2rpx 16rpx rgba(0, 0, 0, 0.3);
  --nav-bg: #0A0E14;
  --tab-bg: #0A0E14;
  --input-bg: rgba(255, 255, 255, 0.04);
  --overlay-card-bg: rgba(15, 29, 38, 0.98);
  --overlay-card-text: #EEF6F7;
  --overlay-card-sub: #A8B7BC;
  --overlay-card-muted: #84969C;
}

page {
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'PingFang SC', 'HarmonyOS Sans', sans-serif;
  font-size: 28rpx;
  -webkit-font-smoothing: antialiased;
  background: var(--bg);
  color: var(--text);
  transition: background 0.3s, color 0.3s;
}

button {
  background: transparent;
  border: none;
  padding: 0;
  margin: 0;
  line-height: normal;
  &::after { border: none; }
}

input { background: transparent; }
.tabular { font-variant-numeric: tabular-nums; }

/* 全局卡片 */
.card {
  background: var(--card);
  border: 1rpx solid var(--card-border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}

/* TabBar 深色覆盖 */
.dark .uni-tabbar, .dark uni-tabbar { background-color: var(--tab-bg) !important; border-top-color: var(--divider) !important; }
.dark .uni-tabbar .uni-tabbar__label, .dark uni-tabbar .uni-tabbar__label { color: var(--text-dim) !important; }
.dark .uni-tabbar .uni-tabbar__item--active .uni-tabbar__label, .dark uni-tabbar .uni-tabbar__item--active .uni-tabbar__label { color: var(--primary) !important; }

/* 导航栏深色 */
.dark .uni-page-head, .dark uni-page-head { background-color: var(--nav-bg) !important; }
.dark .uni-page-head .uni-page-head__title, .dark uni-page-head .uni-page-head__title { color: var(--text) !important; }

/* Input/Switch 深色 */
.dark input, .dark textarea { color: var(--text) !important; }
.dark input::placeholder { color: var(--text-dim) !important; }
</style>
