<template>
  <view class="page" :class="{ 'auth-ready': pageEntered, 'auth-success': loginSucceeded }">
    <view class="auth-ambient" aria-hidden="true"><view class="ambient-glow" /><view class="ambient-ring" /></view>
    <view class="shell" :style="{ paddingTop: 'calc(52rpx + var(--safe-top))' }">
      <view class="logo-area">
        <view class="brand-emblem">
          <view class="brand-orbit" aria-hidden="true" />
          <image class="logo-img" src="/static/logo/logo.png" mode="aspectFit" />
        </view>
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
          <view :key="mode + '-' + authMethod" class="auth-panel-content" :class="{ 'panel-forward': mode === 'register' || authMethod === 'kai' }">
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

        <view class="submit-area" :class="{ 'submit-active': submitting || loginSucceeded }">
          <view class="submit-track">
            <view v-if="loginSucceeded" class="success-ripple" aria-hidden="true" />
            <view class="btn-primary" :class="{ disabled: !agree, busy: submitting, succeeded: loginSucceeded }" role="button" tabindex="0" :aria-label="submitLabel()" :aria-disabled="!agree || submitting || loginSucceeded ? 'true' : 'false'" :aria-busy="submitting && !loginSucceeded ? 'true' : 'false'" @tap="submit" @keydown.enter="submit" @keydown.space.prevent="submit">
              <text class="submit-label" :aria-hidden="submitting || loginSucceeded ? 'true' : 'false'">{{ submitLabel() }}</text>
              <view class="submit-symbol" aria-hidden="true">
                <view v-if="submitting && !loginSucceeded" class="submit-spinner" />
                <view v-if="loginSucceeded" class="submit-check" />
              </view>
            </view>
          </view>
          <view class="submit-status" aria-live="polite">
            <text v-if="submitting || loginSucceeded">{{ submitLabel() }}</text>
          </view>
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
    const result = await startKaiAuth(mode.value, mode.value === 'register' ? form.invite_code : '')
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

function submitLabel() {
  if (loginSucceeded.value) return t('loginSuccess')
  if (authMethod.value === 'phone') return t(submitting.value ? '提交中...' : (mode.value === 'login' ? '登录' : '注册'))
  return t(submitting.value ? 'kaiOpening' : (mode.value === 'login' ? 'kaiAccountLogin' : 'kaiAccountRegister'))
}

function scheduleLoginNavigation() {
  if (loginSuccessTimer) clearTimeout(loginSuccessTimer)
  loginSuccessTimer = null
  if (!pageVisible) return
  loginSuccessTimer = setTimeout(() => {
    loginSuccessTimer = null
    if (pageVisible) enterAuthenticatedApp()
  }, prefersReducedMotion() ? 0 : 520)
}

function completeLogin() {
  loginSucceeded.value = true
  scheduleLoginNavigation()
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
  const incomingInviteCode = String(options?.invite_code ?? options?.invite ?? '').trim().toUpperCase().slice(0, 16)
  if (incomingInviteCode) {
    form.invite_code = incomingInviteCode
    mode.value = 'register'
  }
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
  if (loginSucceeded.value) {
    if (userStore.isLogin) {
      scheduleLoginNavigation()
      return
    }
    loginSucceeded.value = false
  }
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
  if (loginSuccessTimer) clearTimeout(loginSuccessTimer)
  loginSuccessTimer = null
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
.page { position: relative; min-height: 100vh; overflow: hidden; background: var(--bg-2); --auth-ease: cubic-bezier(.22, 1, .36, 1); --auth-spring: cubic-bezier(.2, .85, .25, 1.12); }
.auth-ambient { position: absolute; top: 0; left: 0; right: 0; height: 620rpx; overflow: hidden; pointer-events: none; }
.ambient-glow { position: absolute; width: 740rpx; height: 740rpx; top: -390rpx; right: -200rpx; background: radial-gradient(circle, var(--primary-soft) 0%, transparent 68%); opacity: 0; transform: scale(.85); transition: opacity 700ms ease, transform 900ms var(--auth-ease); }
.ambient-ring { position: absolute; width: 390rpx; height: 390rpx; right: -155rpx; top: -200rpx; border: 1rpx solid var(--primary-soft); border-radius: 50%; }
.auth-ready .ambient-glow { opacity: 1; transform: scale(1); }
.logo-area, .auth-card { opacity: 0; transform: translate3d(0, 28rpx, 0); transition: opacity 260ms ease, transform 620ms var(--auth-ease); }
.auth-card { transition-delay: 55ms; }
.auth-ready .logo-area, .auth-ready .auth-card { opacity: 1; transform: none; }
.shell { position: relative; max-width: 820rpx; margin: 0 auto; padding-left: 36rpx; padding-right: 36rpx; padding-bottom: 48rpx; }
.logo-area { display: flex; align-items: center; margin: 30rpx 12rpx 46rpx; }
.brand-emblem { position: relative; width: 96rpx; height: 96rpx; flex-shrink: 0; margin-right: 26rpx; }
.brand-orbit { position: absolute; inset: -9rpx; border: 1rpx solid var(--primary-soft); border-radius: 34rpx; }
.logo-img { width: 96rpx; height: 96rpx; border-radius: 26rpx; box-shadow: 0 10rpx 28rpx var(--primary-soft); }
.auth-ready .brand-emblem { animation: auth-emblem-in 660ms var(--auth-ease) both; }
@keyframes auth-emblem-in { 0% { transform: scale(.88) rotate(-5deg); } 65% { transform: scale(1.035) rotate(1deg); } 100% { transform: none; } }
.brand-copy { display: flex; flex-direction: column; min-width: 0; }
.logo { font-size: 44rpx; line-height: 1; font-weight: 800; color: var(--text); letter-spacing: 2rpx; }
.sub { margin-top: 12rpx; color: var(--text-sub); font-size: 24rpx; line-height: 1.5; }
.auth-card { background: var(--bg); border: 1rpx solid var(--card-border); border-radius: 36rpx; padding: 28rpx; box-shadow: 0 16rpx 56rpx rgba(15, 38, 47, 0.045); }
.auth-card + .auth-card { margin-top: 20rpx; }
.mode-switch { position: relative; display: grid; grid-template-columns: 1fr 1fr; background: var(--bg-2); border-radius: 18rpx; padding: 6rpx; margin-bottom: 28rpx; }
.mode-indicator { position: absolute; top: 6rpx; bottom: 6rpx; left: 6rpx; width: calc(50% - 6rpx); border-radius: 14rpx; background: var(--bg); box-shadow: 0 5rpx 18rpx rgba(15, 38, 47, 0.08); transition: transform 380ms var(--auth-spring); }
.mode-register .mode-indicator { transform: translateX(100%); }
.mode-item { position: relative; z-index: 1; height: 76rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 28rpx; font-weight: 600; border-radius: 14rpx; transition: color 180ms ease, transform 140ms ease; }
.mode-item.active { color: var(--text); }
.method-switch { position: relative; display: grid; grid-template-columns: 1fr 1fr; gap: 16rpx; margin-bottom: 24rpx; }
.method-indicator { position: absolute; top: 0; bottom: 0; left: 0; width: calc(50% - 8rpx); box-sizing: border-box; border: 1rpx solid var(--primary); border-radius: 16rpx; background: var(--primary-soft); transition: transform 360ms var(--auth-spring); }
.method-kai .method-indicator { transform: translateX(calc(100% + 16rpx)); }
.method-item { position: relative; z-index: 1; min-height: 76rpx; border: 1rpx solid var(--border); border-radius: 16rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 26rpx; transition: color 180ms ease, border-color 180ms ease, transform 140ms ease; }
.method-item.active { color: var(--primary); border-color: transparent; font-weight: 600; }
.mode-item:active, .method-item:active { transform: scale(.97); }
.auth-panel-frame { overflow: hidden; transition: height 380ms var(--auth-ease); }
.auth-panel-content { --panel-from: -16rpx; padding: 5rpx; box-sizing: border-box; animation: auth-panel-in 340ms var(--auth-ease); }
.auth-panel-content.panel-forward { --panel-from: 16rpx; }
@keyframes auth-panel-in { from { opacity: .3; transform: translate3d(var(--panel-from), 0, 0); } to { opacity: 1; transform: none; } }
.field { position: relative; margin-bottom: 22rpx; background: var(--bg-2); border: 1rpx solid var(--border); border-radius: 20rpx; padding: 20rpx 24rpx; transition: border-color 220ms ease, box-shadow 220ms ease, background-color 220ms ease; animation: auth-field-in 440ms var(--auth-ease) both; }
.field:nth-child(2) { animation-delay: 35ms; }
.field:nth-child(3) { animation-delay: 70ms; }
.field:nth-child(4) { animation-delay: 105ms; }
.field:nth-child(5) { animation-delay: 140ms; }
@keyframes auth-field-in { from { opacity: .35; transform: translate3d(0, 10rpx, 0); } to { opacity: 1; transform: none; } }
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
.submit-track { position: relative; min-height: 100rpx; display: flex; align-items: center; justify-content: center; }
.btn-primary { position: relative; width: 100%; height: 100rpx; flex-shrink: 0; display: flex; align-items: center; justify-content: center; box-sizing: border-box; overflow: hidden; background: var(--primary); color: #fff; text-align: center; border-radius: 22rpx; font-size: 30rpx; font-weight: 650; box-shadow: 0 10rpx 24rpx var(--primary-soft); transition: width 380ms var(--auth-ease), border-radius 380ms var(--auth-ease), transform 160ms var(--auth-spring), opacity 180ms ease, background-color 240ms ease, box-shadow 220ms ease; }
.btn-primary:not(.disabled):not(.busy):not(.succeeded):active { transform: scale(.97); box-shadow: 0 4rpx 12rpx var(--primary-soft); }
.btn-primary.disabled { opacity: .45; box-shadow: none; }
.btn-primary.busy, .btn-primary.succeeded { width: 100rpx; border-radius: 50rpx; }
.btn-primary.succeeded { background: #158466; box-shadow: 0 8rpx 24rpx rgba(21,132,102,.16); }
.submit-label { display: block; padding: 0 24rpx; white-space: nowrap; opacity: 1; transform: translateY(0); transition: opacity 120ms ease, transform 180ms ease; }
.busy .submit-label, .succeeded .submit-label { opacity: 0; transform: translateY(10rpx); }
.submit-symbol { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; pointer-events: none; }
.submit-spinner { width: 38rpx; height: 38rpx; box-sizing: border-box; border: 4rpx solid rgba(255,255,255,.28); border-top-color: #fff; border-right-color: #fff; border-radius: 50%; animation: auth-submit-spin 800ms linear infinite; }
.submit-check { width: 20rpx; height: 36rpx; margin-top: -6rpx; border-right: 4rpx solid #fff; border-bottom: 4rpx solid #fff; transform: rotate(45deg); animation: auth-tick-in 320ms var(--auth-spring) both; }
.success-ripple { position: absolute; width: 100rpx; height: 100rpx; border: 2rpx solid rgba(21,132,102,.2); border-radius: 50%; pointer-events: none; animation: auth-success-ring 520ms ease-out both; }
.submit-status { min-height: 32rpx; margin-top: 12rpx; text-align: center; font-size: 23rpx; line-height: 32rpx; color: var(--text-sub); opacity: 0; transform: translateY(6rpx); transition: opacity 180ms ease, transform 240ms var(--auth-ease); }
.submit-active .submit-status { opacity: 1; transform: none; }
.auth-success .submit-status { color: #158466; }
@keyframes auth-submit-spin { to { transform: rotate(360deg); } }
@keyframes auth-check-in { from { transform: scale(.6); opacity: .2; } to { transform: scale(1); opacity: 1; } }
@keyframes auth-tick-in { from { opacity: 0; transform: rotate(45deg) scale(.45); } to { opacity: 1; transform: rotate(45deg) scale(1); } }
@keyframes auth-success-ring { from { transform: scale(.95); opacity: .8; } to { transform: scale(1.65); opacity: 0; } }
.security-note { display: block; text-align: center; color: var(--text-dim); font-size: 21rpx; margin: 20rpx 0 4rpx; }
.contact-link { display: block; width: fit-content; margin: 6rpx auto 0; padding: 8rpx 0; background: transparent; color: var(--primary); font-size: 24rpx; line-height: 1.5; text-decoration: underline; }
.contact-link::after { border: 0; }
@media (prefers-reduced-motion: reduce) {
  .logo-area, .auth-card, .mode-indicator, .mode-item, .method-indicator, .method-item,
  .auth-panel-frame, .field, .flabel, .eye, .check, .btn-primary, .ambient-glow,
  .submit-label, .submit-status { transition: none; }
  .auth-ready .brand-emblem, .auth-panel-content, .field, .ck, .submit-spinner, .submit-check, .success-ripple { animation: none; }
  .success-ripple { display: none; }
  .logo-area, .auth-card { transform: none; }
  .mode-item:active, .method-item:active, .eye:active, .check:active,
  .btn-primary:not(.disabled):not(.busy):not(.succeeded):active { transform: none; }
}
</style>
