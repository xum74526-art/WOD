<template>
  <view class="page" :class="{ 'auth-ready': pageEntered }">
    <view class="shell" :style="{ paddingTop: 'calc(52rpx + var(--safe-top))' }">
      <view class="logo-area">
        <image class="logo-img" src="/static/logo/logo.png" mode="aspectFit" />
        <view class="brand-copy">
          <text class="logo">{{ t('appName') }}</text>
          <text class="sub">{{ t('算力资源撮合平台') }}</text>
        </view>
      </view>

      <view v-if="pendingDeletion" class="auth-card" @tap="openDeletionStatus">
        <text class="alink">{{ t('deletionResume') }}</text>
      </view>
      <view class="auth-card">
        <view class="mode-switch" :class="{ 'mode-register': mode === 'register' }">
          <view class="mode-indicator" aria-hidden="true" />
          <view class="mode-item" :class="{ active: mode === 'login' }" @tap="setMode('login')">{{ t('登录') }}</view>
          <view class="mode-item" :class="{ active: mode === 'register' }" @tap="setMode('register')">{{ t('注册') }}</view>
        </view>

        <view class="method-switch" :class="{ 'method-kai': authMethod === 'kai' }">
          <view class="method-indicator" aria-hidden="true" />
          <view class="method-item" :class="{ active: authMethod === 'phone' }" @tap="setAuthMethod('phone')">
            <text>{{ t(mode === 'login' ? 'phoneLogin' : 'phoneRegister') }}</text>
          </view>
          <view class="method-item" :class="{ active: authMethod === 'kai' }" @tap="setAuthMethod('kai')">
            <text>{{ t(mode === 'login' ? 'kaiLogin' : 'kaiRegister') }}</text>
          </view>
        </view>

        <view class="auth-panel-frame" :style="{ height: panelHeight }">
          <view :key="mode + '-' + authMethod" class="auth-panel-content">
            <view v-if="authMethod === 'phone'" class="phone-form">
              <view class="field" :class="{ focused: focusedField === 'username' }" v-if="mode === 'register'">
                <text class="flabel">{{ t('k_819767ad') }}</text>
                <input class="finput" v-model="form.username" :placeholder="t('k_08b1fa13')" placeholder-class="ph" maxlength="64" :disabled="submitting" @focus="focusedField = 'username'" @blur="focusedField = ''" />
              </view>
              <view class="field" :class="{ focused: focusedField === 'invite' }" v-if="mode === 'register'">
                <text class="flabel">{{ t('k_1dfb714c') }}</text>
                <input class="finput" v-model="form.invite_code" :placeholder="t('k_7f9c3b8d')" placeholder-class="ph" maxlength="16" :disabled="submitting" @focus="focusedField = 'invite'" @blur="focusedField = ''" />
              </view>
              <view class="field" :class="{ focused: focusedField === 'captcha' }" v-if="mode === 'register'">
                <text class="flabel">{{ t('k_b19c3a24') }}</text>
                <view class="captcha-row">
                  <input class="finput captcha-input" v-model="form.captcha_code" :placeholder="t('k_8001cfd7')" placeholder-class="ph" maxlength="6" :disabled="submitting" @focus="focusedField = 'captcha'" @blur="focusedField = ''" />
                  <image v-if="captchaImg" class="captcha-img" :src="captchaImg" @tap="refreshCaptcha()" mode="aspectFit" />
                  <view v-else class="captcha-placeholder" @tap="refreshCaptcha()">{{ t('k_3ca790b3') }}</view>
                </view>
              </view>
              <view class="field" :class="{ focused: focusedField === 'phone' }">
                <text class="flabel">{{ t('k_8098e2b4') }}</text>
                <input class="finput" v-model="form.phone" type="number" :placeholder="t('k_6e4f4b33')" placeholder-class="ph" maxlength="11" :disabled="submitting" @focus="focusedField = 'phone'" @blur="focusedField = ''" />
              </view>
              <view class="field password-field" :class="{ focused: focusedField === 'password' }">
                <text class="flabel">{{ t('k_a8105204') }}</text>
                <input class="finput" v-model="form.password" :password="!showPwd" :placeholder="t('k_e39ffe99')" placeholder-class="ph" maxlength="64" :disabled="submitting" confirm-type="done" @confirm="submit" @focus="focusedField = 'password'" @blur="focusedField = ''" />
                <view class="eye" :class="{ on: showPwd }" @tap="showPwd = !showPwd"><AppIcon name="eye" :size="36" /></view>
              </view>
              <view v-if="mode === 'login'" class="account-recovery-row">
                <button class="account-recovery-link" @tap="openAccountRecovery">{{ t('forgotPassword') }}</button>
              </view>
            </view>

            <view v-else class="kai-panel">
              <view class="kai-mark">KAI</view>
              <text class="kai-title">{{ t(mode === 'login' ? 'kaiAccountLogin' : 'kaiAccountRegister') }}</text>
              <text class="kai-desc">{{ t('kaiIdentityHint') }}</text>
              <view class="kai-flow">
                <view class="flow-dot">1</view><text>{{ t('kaiVerifyStep') }}</text>
                <view class="flow-line" />
                <view />
                <view class="flow-dot">2</view><text>{{ t(mode === 'login' ? 'kaiReturnStep' : 'kaiRegisterReturnStep') }}</text>
              </view>
              <view v-if="kaiConfigured === false" class="config-warning">{{ t('kaiNotConfigured') }}</view>
              <text class="phone-note">{{ t(mode === 'login' ? 'kaiPhoneBindingHint' : 'kaiRegisterBindingHint') }}</text>
            </view>
          </view>
        </view>

        <view class="agree">
          <view class="check" :class="{ checked: agree }" @tap="agree = !agree"><text v-if="agree" class="ck">✓</text></view>
          <view class="atext">{{ t('我已阅读并同意') }}<text class="alink" @tap.stop="goAgreement('agreement')">{{ t('用户协议') }}</text>{{ t('和') }}<text class="alink" @tap.stop="goAgreement('privacy')">{{ t('隐私政策') }}</text></view>
        </view>

        <view class="btn-primary" :class="{ disabled: !agree, busy: submitting, succeeded: loginSucceeded }" role="button" :aria-busy="submitting ? 'true' : 'false'" @tap="submit">
          <view v-if="submitting && !loginSucceeded" class="submit-spinner" aria-hidden="true" />
          <text v-if="loginSucceeded" class="submit-check" aria-hidden="true">✓</text>
          <text v-if="loginSucceeded">{{ t('loginSuccess') }}</text>
          <text v-else-if="authMethod === 'phone'">{{ t(submitting ? '提交中...' : (mode === 'login' ? '登录' : '注册')) }}</text>
          <text v-else>{{ t(submitting ? 'kaiOpening' : (mode === 'login' ? 'kaiAccountLogin' : 'kaiAccountRegister')) }}</text>
        </view>
        <text v-if="authMethod === 'kai'" class="security-note">{{ t('kaiPasswordPrivacy') }}</text>
        <button class="contact-link" @tap="callContactPhone">{{ t('platformContactLink', { phone: t('platformContactNumber') }) }}</button>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { getCurrentInstance, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { onHide, onLoad, onReady, onResize, onShow } from '@dcloudio/uni-app'
import { useUserStore } from '@/store/user'
import { request } from '@/api/request'
import { getKaiAuthConfig, startKaiAuth } from '@/api/user'
import AppIcon from '@/components/AppIcon.vue'
import { useI18nStore } from '@/store/i18n'
import {
  kaiAuthCallbackFingerprint,
  parseKaiAuthQuery,
  parseKaiAuthUrl,
  type KaiAuthCallback,
} from '@/utils/kai-auth-callback'
import {
  clearPendingLoginKaiCallback,
  createPendingKaiLoginIntent,
  peekPendingLoginKaiCallback,
  PENDING_KAI_INTENT_KEY,
} from '@/utils/login-kai-callback'
import { hasInquiryRequestPrefill } from '@/utils/inquiry-request'
import { consumeAuthReturnPath } from '@/utils/auth-return-path'
import { readDeletionReceipt } from '@/utils/account-deletion-receipt'
import { callContactPhone } from '@/utils/contact-phone'
import { navigateTo, switchTab } from '@/utils/nav'
import { finishAppLaunch } from '@/utils/app-launch'
import { prefersReducedMotion } from '@/utils/motion'

const { t } = useI18nStore()
const pageEntered = ref(false)
const focusedField = ref('')
const loginSucceeded = ref(false)
const panelHeight = ref('auto')
const pageInstance = getCurrentInstance()
let panelMeasureGeneration = 0
let entranceTimer: ReturnType<typeof setTimeout> | null = null
let launchRevealTimer: ReturnType<typeof setTimeout> | null = null
let loginSuccessTimer: ReturnType<typeof setTimeout> | null = null
let pageVisible = true
const userStore = useUserStore()
const pendingDeletion = ref(false)
onShow(() => { pendingDeletion.value = !!readDeletionReceipt() })
function openDeletionStatus() { navigateTo('/pages/account-deletion/index') }
const mode = ref<'login' | 'register'>('login')
const authMethod = ref<'phone' | 'kai'>('phone')
const form = reactive({ username: '', phone: '', password: '', invite_code: '', captcha_code: '' })
const captchaImg = ref('')
const captchaKey = ref('')
// The server keeps challenges for 300 seconds; expire locally 30 seconds early.
const CAPTCHA_FRESHNESS_MS = 270_000
let captchaExpiresAt = 0
let captchaExpiryTimer: ReturnType<typeof setTimeout> | null = null
let captchaRefreshPromise: Promise<boolean> | null = null
let captchaReplacementNoticePromise: Promise<boolean> | null = null
let captchaFailureNoticeRequested = false
let captchaPageVisible = true
const showPwd = ref(false)
const agree = ref(false)
const submitting = ref(false)
const kaiConfigured = ref<boolean | null>(null)
const externalKaiAuthorizationPending = ref(false)
let processingKaiCallback = ''
let kaiReturnProbeTimer: ReturnType<typeof setTimeout> | null = null
let kaiReturnProbeGeneration = 0
const HANDLED_KAI_CALLBACK_KEY = 'wod_kai_callback_fingerprint'
const KAI_RETURN_PROBE_DELAYS = [0, 80, 180, 350, 650, 1000, 1600, 2400]

function measureAuthPanel() {
  const generation = ++panelMeasureGeneration
  void nextTick(() => {
    if (!pageVisible || generation !== panelMeasureGeneration) return
    uni.createSelectorQuery().in(pageInstance?.proxy)
      .select('.auth-panel-content').boundingClientRect((result) => {
        if (generation !== panelMeasureGeneration || !pageVisible || Array.isArray(result)) return
        if (result?.height && result.height > 0) panelHeight.value = result.height + 'px'
      }).exec()
  })
}

watch([mode, authMethod, kaiConfigured], measureAuthPanel, { flush: 'post' })
onResize(measureAuthPanel)

function setMode(value: 'login' | 'register') {
  if (mode.value === value || submitting.value || loginSucceeded.value) return
  focusedField.value = ''
  mode.value = value
  syncCaptchaLifecycle(false)
}

function setAuthMethod(value: 'phone' | 'kai') {
  if (authMethod.value === value || submitting.value || loginSucceeded.value) return
  focusedField.value = ''
  authMethod.value = value
  syncCaptchaLifecycle(false)
}

function goAgreement(type: string) {
  navigateTo('/pages/agreement/index?type=' + type)
}

function openAccountRecovery() {
  navigateTo('/pages/forgot-password/index')
}

function isPhoneRegistration() {
  return mode.value === 'register' && authMethod.value === 'phone'
}

function stopCaptchaExpiryTimer() {
  if (captchaExpiryTimer) clearTimeout(captchaExpiryTimer)
  captchaExpiryTimer = null
}

function hasFreshCaptcha(now = Date.now()) {
  const remaining = captchaExpiresAt - now
  return !!captchaKey.value && !!captchaImg.value && remaining > 0 && remaining <= CAPTCHA_FRESHNESS_MS
}

function scheduleCaptchaExpiry() {
  stopCaptchaExpiryTimer()
  if (!captchaPageVisible || !isPhoneRegistration() || !hasFreshCaptcha()) return
  captchaExpiryTimer = setTimeout(() => {
    captchaExpiryTimer = null
    if (!captchaPageVisible || !isPhoneRegistration()) return
    if (hasFreshCaptcha()) {
      scheduleCaptchaExpiry()
      return
    }
    syncCaptchaLifecycle(true)
  }, Math.max(0, captchaExpiresAt - Date.now()))
}

function syncCaptchaLifecycle(silent: boolean) {
  stopCaptchaExpiryTimer()
  if (!isPhoneRegistration()) return
  if (!hasFreshCaptcha()) {
    if (form.captcha_code) void refreshCaptchaWithNotice(false)
    else void refreshCaptcha(silent)
    return
  }
  scheduleCaptchaExpiry()
}

async function refreshCaptcha(silent = false): Promise<boolean> {
  if (captchaRefreshPromise) return captchaRefreshPromise
  stopCaptchaExpiryTimer()
  captchaExpiresAt = 0
  captchaKey.value = ''
  captchaImg.value = ''
  form.captcha_code = ''
  captchaRefreshPromise = (async () => {
    try {
      const res = await request<{ key: string; image: string }>({ url: '/auth/captcha', silent })
      captchaKey.value = res.key
      captchaImg.value = res.image
      captchaExpiresAt = Date.now() + CAPTCHA_FRESHNESS_MS
      scheduleCaptchaExpiry()
      return true
    } catch {
      // Keep the captcha empty so an old or uncertain challenge cannot be submitted.
      return false
    } finally {
      captchaRefreshPromise = null
    }
  })()
  return captchaRefreshPromise
}

function refreshCaptchaWithNotice(showFailure: boolean): Promise<boolean> {
  captchaFailureNoticeRequested = captchaFailureNoticeRequested || showFailure
  if (captchaReplacementNoticePromise) return captchaReplacementNoticePromise
  captchaReplacementNoticePromise = (async () => {
    try {
      const refreshed = await refreshCaptcha(true)
      if (captchaPageVisible && isPhoneRegistration()) {
        if (refreshed) {
          uni.showToast({ title: t('registrationCaptchaRefreshed'), icon: 'none' })
        } else if (captchaFailureNoticeRequested) {
          uni.showToast({ title: t('registrationCaptchaLoadFailed'), icon: 'none' })
        }
      }
      return refreshed
    } finally {
      captchaReplacementNoticePromise = null
      captchaFailureNoticeRequested = false
    }
  })()
  return captchaReplacementNoticePromise
}

async function checkKaiConfig() {
  try {
    const config = await getKaiAuthConfig()
    kaiConfigured.value = config.configured
  } catch {
    kaiConfigured.value = null
  }
}

function openExternalAuthorization(url: string) {
  let opened = false
  // #ifdef H5
  window.location.assign(url)
  opened = true
  // #endif
  // #ifdef APP-PLUS
  plus.runtime.openURL(url)
  opened = true
  // #endif
  // #ifndef H5
  // #ifndef APP-PLUS
  uni.setClipboardData({ data: url })
  uni.showToast({ title: t('kaiLinkCopied'), icon: 'none' })
  opened = true
  // #endif
  // #endif
  return opened
}

async function submitKai() {
  if (kaiConfigured.value === false) {
    uni.showToast({ title: t('kaiNotConfigured'), icon: 'none' })
    return
  }
  submitting.value = true
  try {
    const result = await startKaiAuth(mode.value)
    uni.setStorageSync(PENDING_KAI_INTENT_KEY, createPendingKaiLoginIntent(mode.value))
    externalKaiAuthorizationPending.value = true
    if (!openExternalAuthorization(result.authorization_url)) {
      uni.removeStorageSync(PENDING_KAI_INTENT_KEY)
      externalKaiAuthorizationPending.value = false
      submitting.value = false
    }
  } catch {
    uni.removeStorageSync(PENDING_KAI_INTENT_KEY)
    externalKaiAuthorizationPending.value = false
    submitting.value = false
  }
}

async function handleKaiCallback(callback: KaiAuthCallback | null) {
  if (!callback) return false
  const fingerprint = kaiAuthCallbackFingerprint(callback)
  if (fingerprint === processingKaiCallback) return true
  if (uni.getStorageSync(HANDLED_KAI_CALLBACK_KEY) === fingerprint) {
    clearPendingLoginKaiCallback(callback)
    externalKaiAuthorizationPending.value = false
    submitting.value = false
    return true
  }

  processingKaiCallback = fingerprint
  externalKaiAuthorizationPending.value = false
  submitting.value = true
  authMethod.value = 'kai'
  try {
    if (callback.error) {
      uni.setStorageSync(HANDLED_KAI_CALLBACK_KEY, fingerprint)
      uni.removeStorageSync(PENDING_KAI_INTENT_KEY)
      clearPendingLoginKaiCallback(callback)
      const errorKey = callback.error === 'access_denied'
        ? 'kaiCancelled'
        : callback.error === 'terms_required'
          ? '请先同意协议'
          : 'kaiLoginFailed'
      uni.showToast({ title: t(errorKey), icon: 'none' })
      return true
    }
    if (!callback.ticket) return false
    await userStore.loginWithKaiTicket(callback.ticket)
    uni.removeStorageSync(PENDING_KAI_INTENT_KEY)
    uni.setStorageSync(HANDLED_KAI_CALLBACK_KEY, fingerprint)
    clearPendingLoginKaiCallback(callback)
    completeLogin()
    return true
  } catch {
    // Keep the callback retryable when ticket exchange failed because of a
    // temporary network problem. The backend still enforces one-time tickets.
    return true
  } finally {
    processingKaiCallback = ''
    submitting.value = false
  }
}

function handleStagedKaiCallback() {
  const callback = peekPendingLoginKaiCallback()
  if (!callback) return false
  void handleKaiCallback(callback)
  return true
}

let authenticatedNavigationStarted = false

function completeLogin() {
  loginSucceeded.value = true
  loginSuccessTimer = setTimeout(enterAuthenticatedApp, prefersReducedMotion() ? 0 : 280)
}

function enterAuthenticatedApp() {
  if (authenticatedNavigationStarted || !userStore.isLogin || !userStore.authReady) return
  authenticatedNavigationStarted = true
  const returnPath = consumeAuthReturnPath()
  if (hasInquiryRequestPrefill()) {
    uni.reLaunch({ url: '/pages/buy-request/index?compose=1' })
    return
  }
  if (returnPath) {
    uni.reLaunch({
      url: returnPath,
      fail: () => uni.reLaunch({ url: '/pages/index/index' }),
    })
    return
  }
  switchTab('/pages/index/index', { fallbackToReLaunch: true })
}

function runtimeKaiCallback() {
  let callback: KaiAuthCallback | null = null
  // #ifdef APP-PLUS
  callback = parseKaiAuthUrl(plus.runtime.arguments)
  // #endif
  return callback
}

function stopKaiReturnProbe() {
  kaiReturnProbeGeneration += 1
  if (kaiReturnProbeTimer) clearTimeout(kaiReturnProbeTimer)
  kaiReturnProbeTimer = null
}

function probeKaiReturnCallback() {
  stopKaiReturnProbe()
  const generation = kaiReturnProbeGeneration

  const probe = (index: number) => {
    if (generation !== kaiReturnProbeGeneration) return
    const callback = runtimeKaiCallback()
    if (callback) {
      const fingerprint = kaiAuthCallbackFingerprint(callback)
      const handled = uni.getStorageSync(HANDLED_KAI_CALLBACK_KEY) === fingerprint
      // iOS may fire onShow before plus.runtime.arguments is refreshed. The
      // old callback can therefore still be visible briefly; keep waiting for
      // the new ticket instead of treating the stale value as this login.
      if (!handled && fingerprint !== processingKaiCallback) {
        void handleKaiCallback(callback)
        return
      }
    }

    const nextIndex = index + 1
    if (nextIndex < KAI_RETURN_PROBE_DELAYS.length) {
      const delay = KAI_RETURN_PROBE_DELAYS[nextIndex] - KAI_RETURN_PROBE_DELAYS[index]
      kaiReturnProbeTimer = setTimeout(() => probe(nextIndex), delay)
      return
    }
    if (externalKaiAuthorizationPending.value) {
      externalKaiAuthorizationPending.value = false
      submitting.value = false
    }
  }

  probe(0)
}

function registerKaiRuntimeListener() {
  // Some iOS runtime versions deliver the refreshed scheme arguments through
  // newintent after onShow. Listening to both paths avoids a timing dependency.
  // #ifdef APP-PLUS
  const globalEvent = (plus as unknown as {
    globalEvent?: { addEventListener(event: string, listener: () => void): void }
  }).globalEvent
  globalEvent?.addEventListener('newintent', probeKaiReturnCallback)
  // #endif
}

function unregisterKaiRuntimeListener() {
  // #ifdef APP-PLUS
  const globalEvent = (plus as unknown as {
    globalEvent?: { removeEventListener(event: string, listener: () => void): void }
  }).globalEvent
  globalEvent?.removeEventListener('newintent', probeKaiReturnCallback)
  // #endif
}

async function submit() {
  if (submitting.value || loginSucceeded.value) return
  if (!agree.value) { uni.showToast({ title: t('请先同意协议'), icon: 'none' }); return }
  if (authMethod.value === 'kai') { await submitKai(); return }
  const isRegistration = mode.value === 'register'
  const normalizedPhone = form.phone.trim()
  const registrationUsername = form.username.trim()
  const registrationInviteCode = form.invite_code.trim().toUpperCase()
  if (!normalizedPhone || !form.password) { uni.showToast({ title: t('pleaseComplete'), icon: 'none' }); return }
  if (!/^1\d{10}$/.test(normalizedPhone)) { uni.showToast({ title: t('请输入正确手机号'), icon: 'none' }); return }
  if (isRegistration && (registrationUsername.length < 2 || registrationUsername.length > 64)) { uni.showToast({ title: t('registrationUsernameLength'), icon: 'none' }); return }
  if (isRegistration && (form.password.length < 6 || form.password.length > 64)) { uni.showToast({ title: t('registrationPasswordLength'), icon: 'none' }); return }
  if (isRegistration && registrationInviteCode.length > 16) { uni.showToast({ title: t('registrationInviteCodeLength'), icon: 'none' }); return }
  if (isRegistration && !hasFreshCaptcha()) {
    submitting.value = true
    await refreshCaptchaWithNotice(true)
    submitting.value = false
    return
  }
  if (isRegistration && !form.captcha_code) { uni.showToast({ title: t('请输入验证码'), icon: 'none' }); return }
  submitting.value = true
  try {
    if (!isRegistration) await userStore.login(normalizedPhone, form.password)
    else await userStore.register(registrationUsername, normalizedPhone, form.password, registrationInviteCode || undefined, captchaKey.value, form.captcha_code)
    completeLogin()
  } catch {
    if (isRegistration) await refreshCaptcha(true)
  }
  submitting.value = false
}

onLoad((options) => {
  const callback = parseKaiAuthQuery(options)
  if (callback) void handleKaiCallback(callback)
  else handleStagedKaiCallback()
})

function revealRenderedLogin(attempt = 0) {
  // onReady is a service-layer event on native. Wait for the view layer to
  // acknowledge visible content before removing its cover, otherwise the
  // bridge delay can expose an empty page even though the route is ready.
  void nextTick(() => {
    if (!pageVisible) return
    uni.createSelectorQuery().in(pageInstance?.proxy).select('.auth-card')
      .fields({ computedStyle: ['opacity'] }, (result) => {
        if (!pageVisible) return
        const opacity = Number((result as { opacity?: string } | undefined)?.opacity ?? 0)
        if (opacity >= 0.35 || attempt >= 12) {
          finishAppLaunch()
          return
        }
        launchRevealTimer = setTimeout(() => {
          launchRevealTimer = null
          revealRenderedLogin(attempt + 1)
        }, 40)
      }).exec()
  })
}

onReady(() => {
  // The background is always opaque; only the brand and form enter, once.
  measureAuthPanel()
  entranceTimer = setTimeout(() => {
    entranceTimer = null
    pageEntered.value = true
    revealRenderedLogin()
  }, prefersReducedMotion() ? 0 : 32)
})

async function restoreExistingSession() {
  await userStore.restore()
  if (pageVisible && userStore.isLogin && !loginSucceeded.value) enterAuthenticatedApp()
}

onShow(() => {
  pageVisible = true
  measureAuthPanel()
  captchaPageVisible = true
  if (userStore.isLogin) {
    clearPendingLoginKaiCallback()
    stopCaptchaExpiryTimer()
    void restoreExistingSession()
    return
  }
  syncCaptchaLifecycle(true)
  if (!handleStagedKaiCallback()) probeKaiReturnCallback()
})

onHide(() => {
  pageVisible = false
  captchaPageVisible = false
  stopCaptchaExpiryTimer()
})

onMounted(() => {
  uni.$on('wod-kai-login-callback-ready', handleStagedKaiCallback)
  registerKaiRuntimeListener()
  void checkKaiConfig()
})
onUnmounted(() => {
  pageVisible = false
  panelMeasureGeneration += 1
  if (entranceTimer) clearTimeout(entranceTimer)
  if (launchRevealTimer) clearTimeout(launchRevealTimer)
  if (loginSuccessTimer) clearTimeout(loginSuccessTimer)
  captchaPageVisible = false
  stopCaptchaExpiryTimer()
  uni.$off('wod-kai-login-callback-ready', handleStagedKaiCallback)
  unregisterKaiRuntimeListener()
  stopKaiReturnProbe()
})
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg-2); }
.logo-area, .auth-card { opacity: 0; transform: translate3d(0, 18rpx, 0); transition: opacity 420ms ease, transform 480ms cubic-bezier(.22, 1, .36, 1); }
.auth-card { transition-delay: 65ms; }
.auth-ready .logo-area, .auth-ready .auth-card { opacity: 1; transform: none; }
.shell { padding-left: 36rpx; padding-right: 36rpx; padding-bottom: 48rpx; }
.logo-area { display: flex; align-items: center; margin: 28rpx 8rpx 40rpx; }
.logo-img { width: 88rpx; height: 88rpx; border-radius: 22rpx; margin-right: 22rpx; }
.brand-copy { display: flex; flex-direction: column; }
.logo { font-size: 44rpx; line-height: 1; font-weight: 800; color: var(--text); letter-spacing: 2rpx; }
.sub { margin-top: 12rpx; color: var(--text-sub); font-size: 24rpx; }
.auth-card { background: var(--card); border: 1rpx solid var(--border); border-radius: 28rpx; padding: 24rpx; box-shadow: 0 14rpx 42rpx rgba(15, 38, 47, 0.06); }
.mode-switch { position: relative; display: grid; grid-template-columns: 1fr 1fr; background: var(--bg-2); border-radius: 18rpx; padding: 6rpx; margin-bottom: 28rpx; }
.mode-indicator { position: absolute; top: 6rpx; bottom: 6rpx; left: 6rpx; width: calc(50% - 6rpx); border-radius: 14rpx; background: var(--bg); box-shadow: 0 5rpx 18rpx rgba(15, 38, 47, 0.08); transition: transform 280ms cubic-bezier(.22, 1, .36, 1); }
.mode-register .mode-indicator { transform: translateX(100%); }
.mode-item { position: relative; z-index: 1; height: 76rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 28rpx; font-weight: 600; border-radius: 14rpx; transition: color 180ms ease, transform 140ms ease; }
.mode-item.active { color: var(--text); }
.method-switch { position: relative; display: grid; grid-template-columns: 1fr 1fr; gap: 16rpx; margin-bottom: 24rpx; }
.method-indicator { position: absolute; top: 0; bottom: 0; left: 0; width: calc(50% - 8rpx); box-sizing: border-box; border: 1rpx solid var(--primary); border-radius: 16rpx; background: var(--primary-soft); transition: transform 260ms cubic-bezier(.22, 1, .36, 1); }
.method-kai .method-indicator { transform: translateX(calc(100% + 16rpx)); }
.method-item { position: relative; z-index: 1; min-height: 76rpx; border: 1rpx solid var(--border); border-radius: 16rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 26rpx; transition: color 180ms ease, border-color 180ms ease, transform 140ms ease; }
.method-item.active { color: var(--primary); border-color: transparent; font-weight: 600; }
.mode-item:active, .method-item:active { transform: scale(.97); }
.auth-panel-frame { overflow: hidden; transition: height 280ms cubic-bezier(.22, 1, .36, 1); }
.auth-panel-content { padding: 4rpx; box-sizing: border-box; animation: auth-panel-in 240ms cubic-bezier(.22, 1, .36, 1); }
@keyframes auth-panel-in { from { opacity: .45; transform: translate3d(0, 8rpx, 0); } to { opacity: 1; transform: none; } }
.field { position: relative; margin-bottom: 22rpx; background: var(--bg-2); border: 1rpx solid var(--border); border-radius: 16rpx; padding: 20rpx 24rpx; transition: border-color 180ms ease, box-shadow 180ms ease, background-color 180ms ease; }
.field.focused { border-color: var(--primary); box-shadow: 0 0 0 4rpx var(--primary-soft); background: var(--bg); }
.field.focused .flabel { color: var(--primary); }
.flabel { color: var(--text-sub); font-size: 22rpx; display: block; margin-bottom: 10rpx; transition: color 180ms ease; }
.password-field .finput { padding-right: 58rpx; }
.finput { color: var(--text); font-size: 30rpx; min-height: 42rpx; }
.ph { color: var(--text-dim); }
.captcha-row { display: flex; align-items: center; gap: 16rpx; }
.captcha-input { flex: 1; }
.captcha-img { width: 112px; height: 46px; border-radius: 8rpx; flex-shrink: 0; }
.captcha-placeholder { width: 112px; height: 46px; border-radius: 8rpx; background: var(--card); border: 1rpx solid var(--border); display: flex; align-items: center; justify-content: center; font-size: 22rpx; color: var(--text-sub); flex-shrink: 0; }
.eye { position: absolute; right: 16rpx; bottom: 17rpx; padding: 10rpx; color: var(--text-sub); transition: color 160ms ease, transform 140ms ease; }
.eye:active { transform: scale(.88); }
.eye.on { color: var(--primary); }
.account-recovery-row { display: flex; justify-content: flex-end; margin: -8rpx 2rpx 4rpx; }
.account-recovery-link { width: auto; margin: 0; padding: 8rpx 0; background: transparent; color: var(--primary); font-size: 24rpx; line-height: 1.4; }
.account-recovery-link::after { border: 0; }
.kai-panel { padding: 20rpx 8rpx 8rpx; display: flex; flex-direction: column; align-items: center; text-align: center; }
.kai-mark { width: 100rpx; height: 100rpx; border-radius: 24rpx; display: flex; align-items: center; justify-content: center; background: #15272d; color: #fff; font-size: 24rpx; font-weight: 800; letter-spacing: 2rpx; box-shadow: inset 0 0 0 1rpx rgba(255,255,255,.12); }
.kai-title { margin-top: 24rpx; font-size: 32rpx; font-weight: 700; color: var(--text); }
.kai-desc { margin-top: 12rpx; color: var(--text-sub); font-size: 24rpx; line-height: 1.6; max-width: 540rpx; }
.kai-flow { width: 100%; box-sizing: border-box; margin-top: 28rpx; padding: 22rpx 24rpx; border-radius: 16rpx; background: var(--bg-2); display: grid; grid-template-columns: 36rpx 1fr; gap: 10rpx 14rpx; align-items: center; text-align: left; color: var(--text-sub); font-size: 23rpx; }
.flow-dot { width: 34rpx; height: 34rpx; border-radius: 50%; background: var(--primary); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 20rpx; }
.flow-line { width: 2rpx; height: 18rpx; background: var(--border); justify-self: center; }
.config-warning { width: 100%; box-sizing: border-box; margin-top: 20rpx; padding: 18rpx; background: rgba(239, 68, 68, .08); color: #dc2626; border-radius: 14rpx; font-size: 23rpx; }
.phone-note { margin-top: 20rpx; color: var(--text-dim); font-size: 22rpx; }
.agree { display: flex; align-items: flex-start; margin: 28rpx 4rpx 28rpx; }
.check { width: 36rpx; height: 36rpx; border-radius: 18rpx; border: 1rpx solid var(--text-dim); margin-right: 14rpx; display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: background-color 160ms ease, border-color 160ms ease, transform 140ms ease; }
.check:active { transform: scale(.88); }
.check.checked { background: var(--primary); border-color: var(--primary); }
.ck { color: #fff; font-size: 22rpx; animation: auth-check-in 180ms ease-out; }
.atext { color: var(--text-sub); font-size: 23rpx; flex: 1; line-height: 1.55; }
.alink { color: var(--primary); }
.btn-primary { display: flex; align-items: center; justify-content: center; gap: 16rpx; min-height: 96rpx; box-sizing: border-box; background: var(--primary); color: #fff; text-align: center; padding: 27rpx 20rpx; border-radius: 16rpx; font-size: 30rpx; font-weight: 650; transition: transform 140ms ease, opacity 180ms ease, background-color 200ms ease, box-shadow 180ms ease; }
.btn-primary:not(.disabled):not(.busy):not(.succeeded):active { transform: scale(.98); box-shadow: 0 4rpx 18rpx var(--primary-soft); }
.btn-primary.disabled { opacity: 0.4; }
.btn-primary.succeeded { background: #158466; }
.submit-spinner { width: 28rpx; height: 28rpx; border: 3rpx solid rgba(255,255,255,.35); border-top-color: #fff; border-radius: 50%; animation: auth-submit-spin 750ms linear infinite; }
.submit-check { animation: auth-check-in 180ms ease-out; }
@keyframes auth-submit-spin { to { transform: rotate(360deg); } }
@keyframes auth-check-in { from { transform: scale(.6); opacity: .2; } to { transform: scale(1); opacity: 1; } }
.security-note { display: block; text-align: center; color: var(--text-dim); font-size: 21rpx; margin: 20rpx 0 4rpx; }
.contact-link { display: block; width: fit-content; margin: 20rpx auto 0; padding: 8rpx 0; background: transparent; color: var(--primary); font-size: 24rpx; line-height: 1.5; text-decoration: underline; }
.contact-link::after { border: 0; }
@media (prefers-reduced-motion: reduce) {
  .logo-area, .auth-card, .mode-indicator, .mode-item, .method-indicator, .method-item,
  .auth-panel-frame, .field, .flabel, .eye, .check, .btn-primary { transition: none; }
  .auth-panel-content, .ck, .submit-spinner, .submit-check { animation: none; }
  .logo-area, .auth-card { transform: none; }
  .mode-item:active, .method-item:active, .eye:active, .check:active,
  .btn-primary:not(.disabled):not(.busy):not(.succeeded):active { transform: none; }
}
</style>
