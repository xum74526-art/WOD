<template>
  <view class="page">
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
        <view class="mode-switch">
          <view class="mode-item" :class="{ active: mode === 'login' }" @tap="setMode('login')">{{ t('登录') }}</view>
          <view class="mode-item" :class="{ active: mode === 'register' }" @tap="setMode('register')">{{ t('注册') }}</view>
        </view>

        <view class="method-switch">
          <view class="method-item" :class="{ active: authMethod === 'phone' }" @tap="setAuthMethod('phone')">
            <text>{{ t(mode === 'login' ? 'phoneLogin' : 'phoneRegister') }}</text>
          </view>
          <view class="method-item" :class="{ active: authMethod === 'kai' }" @tap="setAuthMethod('kai')">
            <text>{{ t(mode === 'login' ? 'kaiLogin' : 'kaiRegister') }}</text>
          </view>
        </view>

        <view v-if="authMethod === 'phone'" class="phone-form">
          <view class="field" v-if="mode === 'register'">
            <text class="flabel">{{ t('k_819767ad') }}</text>
            <input class="finput" v-model="form.username" :placeholder="t('k_08b1fa13')" placeholder-class="ph" />
          </view>
          <view class="field" v-if="mode === 'register'">
            <text class="flabel">{{ t('k_1dfb714c') }}</text>
            <input class="finput" v-model="form.invite_code" :placeholder="t('k_7f9c3b8d')" placeholder-class="ph" />
          </view>
          <view class="field" v-if="mode === 'register'">
            <text class="flabel">{{ t('k_b19c3a24') }}</text>
            <view class="captcha-row">
              <input class="finput captcha-input" v-model="form.captcha_code" :placeholder="t('k_8001cfd7')" placeholder-class="ph" maxlength="6" />
              <image v-if="captchaImg" class="captcha-img" :src="captchaImg" @tap="refreshCaptcha" mode="aspectFit" />
              <view v-else class="captcha-placeholder" @tap="refreshCaptcha">{{ t('k_3ca790b3') }}</view>
            </view>
          </view>
          <view class="field">
            <text class="flabel">{{ t('k_8098e2b4') }}</text>
            <input class="finput" v-model="form.phone" type="number" :placeholder="t('k_6e4f4b33')" placeholder-class="ph" maxlength="11" />
          </view>
          <view class="field">
            <text class="flabel">{{ t('k_a8105204') }}</text>
            <input class="finput" v-model="form.password" :password="!showPwd" :placeholder="t('k_e39ffe99')" placeholder-class="ph" />
            <view class="eye" :class="{ on: showPwd }" @tap="showPwd = !showPwd"><AppIcon name="eye" :size="36" /></view>
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

        <view class="agree">
          <view class="check" :class="{ checked: agree }" @tap="agree = !agree"><text v-if="agree" class="ck">✓</text></view>
          <view class="atext">{{ t('我已阅读并同意') }}<text class="alink" @tap.stop="goAgreement('agreement')">{{ t('用户协议') }}</text>{{ t('和') }}<text class="alink" @tap.stop="goAgreement('privacy')">{{ t('隐私政策') }}</text></view>
        </view>

        <view class="btn-primary" :class="{ disabled: submitting || !agree }" @tap="submit">
          <text v-if="authMethod === 'phone'">{{ t(submitting ? '提交中...' : (mode === 'login' ? '登录' : '注册')) }}</text>
          <text v-else>{{ t(submitting ? 'kaiOpening' : (mode === 'login' ? 'kaiAccountLogin' : 'kaiAccountRegister')) }}</text>
        </view>
        <text v-if="authMethod === 'kai'" class="security-note">{{ t('kaiPasswordPrivacy') }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
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
import { hasInquiryRequestPrefill } from '@/utils/inquiry-request'
import { readDeletionReceipt } from '@/utils/account-deletion-receipt'

const { t } = useI18nStore()
const userStore = useUserStore()
const pendingDeletion = ref(false)
onShow(() => { pendingDeletion.value = !!readDeletionReceipt() })
function openDeletionStatus() { uni.navigateTo({ url: '/pages/account-deletion/index' }) }
const mode = ref<'login' | 'register'>('login')
const authMethod = ref<'phone' | 'kai'>('phone')
const form = reactive({ username: '', phone: '', password: '', invite_code: '', captcha_code: '' })
const captchaImg = ref('')
const captchaKey = ref('')
const showPwd = ref(false)
const agree = ref(false)
const submitting = ref(false)
const kaiConfigured = ref<boolean | null>(null)
const externalKaiAuthorizationPending = ref(false)
let processingKaiCallback = ''
let kaiReturnProbeTimer: ReturnType<typeof setTimeout> | null = null
let kaiReturnProbeGeneration = 0
const HANDLED_KAI_CALLBACK_KEY = 'wod_kai_callback_fingerprint'
const PENDING_KAI_INTENT_KEY = 'wod_kai_auth_intent'
const KAI_RETURN_PROBE_DELAYS = [0, 80, 180, 350, 650, 1000, 1600, 2400]

function setMode(value: 'login' | 'register') {
  mode.value = value
  if (value === 'register') authMethod.value = 'phone'
  if (value === 'register' && authMethod.value === 'phone' && !captchaImg.value) refreshCaptcha()
}

function setAuthMethod(value: 'phone' | 'kai') {
  authMethod.value = value
  if (value === 'phone' && mode.value === 'register' && !captchaImg.value) refreshCaptcha()
}

function goAgreement(type: string) {
  uni.navigateTo({ url: '/pages/agreement/index?type=' + type })
}

async function refreshCaptcha() {
  try {
    const res = await request<{ key: string; image: string }>({ url: '/auth/captcha' })
    captchaKey.value = res.key
    captchaImg.value = res.image
  } catch {}
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
    uni.setStorageSync(PENDING_KAI_INTENT_KEY, mode.value)
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
    externalKaiAuthorizationPending.value = false
    submitting.value = false
    return true
  }

  processingKaiCallback = fingerprint
  externalKaiAuthorizationPending.value = false
  submitting.value = true
  authMethod.value = 'kai'
  const pendingKaiIntent = uni.getStorageSync(PENDING_KAI_INTENT_KEY) === 'register' ? 'register' : 'login'
  try {
    if (callback.error) {
      uni.setStorageSync(HANDLED_KAI_CALLBACK_KEY, fingerprint)
      uni.removeStorageSync(PENDING_KAI_INTENT_KEY)
      if (callback.error === 'identity_not_bound' && pendingKaiIntent === 'register') {
        mode.value = 'register'
        authMethod.value = 'phone'
        if (!captchaImg.value) void refreshCaptcha()
        uni.showToast({ title: t('kaiRegisterContinuePhone'), icon: 'none', duration: 2600 })
        return true
      }
      const errorKey = callback.error === 'access_denied'
        ? 'kaiCancelled'
        : callback.error === 'identity_not_bound'
          ? 'kaiIdentityNotBoundLogin'
          : 'kaiLoginFailed'
      uni.showToast({ title: t(errorKey), icon: 'none' })
      return true
    }
    if (!callback.ticket) return false
    await userStore.loginWithKaiTicket(callback.ticket)
    uni.removeStorageSync(PENDING_KAI_INTENT_KEY)
    uni.setStorageSync(HANDLED_KAI_CALLBACK_KEY, fingerprint)
    uni.showToast({ title: t('loginSuccess'), icon: 'success' })
    setTimeout(enterAuthenticatedApp, 500)
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

function enterAuthenticatedApp() {
  if (hasInquiryRequestPrefill()) {
    uni.reLaunch({ url: '/pages/buy-request/index?new=1' })
    return
  }
  uni.switchTab({
    url: '/pages/index/index',
    fail: () => uni.reLaunch({ url: '/pages/index/index' }),
  })
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
  if (submitting.value) return
  if (!agree.value) { uni.showToast({ title: t('请先同意协议'), icon: 'none' }); return }
  if (authMethod.value === 'kai') { await submitKai(); return }
  if (!form.phone || !form.password) { uni.showToast({ title: t('pleaseComplete'), icon: 'none' }); return }
  if (mode.value === 'register' && !form.username) { uni.showToast({ title: t('k_08b1fa13'), icon: 'none' }); return }
  if (mode.value === 'register' && !form.captcha_code) { uni.showToast({ title: t('请输入验证码'), icon: 'none' }); return }
  submitting.value = true
  try {
    if (mode.value === 'login') await userStore.login(form.phone, form.password)
    else await userStore.register(form.username, form.phone, form.password, form.invite_code || undefined, captchaKey.value, form.captcha_code)
    uni.showToast({ title: t('success'), icon: 'success' })
    setTimeout(enterAuthenticatedApp, 500)
  } catch { /* request toast */ }
  submitting.value = false
}

onLoad((options) => {
  void handleKaiCallback(parseKaiAuthQuery(options))
})

onShow(() => {
  if (userStore.isLogin) {
    setTimeout(enterAuthenticatedApp, 800)
    return
  }
  probeKaiReturnCallback()
})

onMounted(() => {
  registerKaiRuntimeListener()
  void checkKaiConfig()
})
onUnmounted(() => {
  unregisterKaiRuntimeListener()
  stopKaiReturnProbe()
})
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg-2); }
.shell { padding-left: 36rpx; padding-right: 36rpx; padding-bottom: 48rpx; }
.logo-area { display: flex; align-items: center; margin: 28rpx 8rpx 40rpx; }
.logo-img { width: 88rpx; height: 88rpx; border-radius: 22rpx; margin-right: 22rpx; }
.brand-copy { display: flex; flex-direction: column; }
.logo { font-size: 44rpx; line-height: 1; font-weight: 800; color: var(--text); letter-spacing: 2rpx; }
.sub { margin-top: 12rpx; color: var(--text-sub); font-size: 24rpx; }
.auth-card { background: var(--card); border: 1rpx solid var(--border); border-radius: 28rpx; padding: 24rpx; box-shadow: 0 14rpx 42rpx rgba(15, 38, 47, 0.06); }
.mode-switch { display: grid; grid-template-columns: 1fr 1fr; background: var(--bg-2); border-radius: 18rpx; padding: 6rpx; margin-bottom: 28rpx; }
.mode-item { height: 76rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 28rpx; font-weight: 600; border-radius: 14rpx; }
.mode-item.active { color: var(--text); background: var(--card); box-shadow: 0 5rpx 18rpx rgba(15, 38, 47, 0.08); }
.method-switch { display: grid; grid-template-columns: 1fr 1fr; gap: 16rpx; margin-bottom: 28rpx; }
.method-item { min-height: 76rpx; border: 1rpx solid var(--border); border-radius: 16rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 26rpx; }
.method-item.active { color: var(--primary); background: rgba(24, 175, 196, .08); border-color: var(--primary); font-weight: 600; }
.field { position: relative; margin-bottom: 22rpx; background: var(--bg-2); border: 1rpx solid var(--border); border-radius: 16rpx; padding: 20rpx 24rpx; }
.flabel { color: var(--text-sub); font-size: 22rpx; display: block; margin-bottom: 10rpx; }
.finput { color: var(--text); font-size: 30rpx; min-height: 42rpx; }
.ph { color: var(--text-dim); }
.captcha-row { display: flex; align-items: center; gap: 16rpx; }
.captcha-input { flex: 1; }
.captcha-img { width: 112px; height: 46px; border-radius: 8rpx; flex-shrink: 0; }
.captcha-placeholder { width: 112px; height: 46px; border-radius: 8rpx; background: var(--card); border: 1rpx solid var(--border); display: flex; align-items: center; justify-content: center; font-size: 22rpx; color: var(--text-sub); flex-shrink: 0; }
.eye { position: absolute; right: 24rpx; bottom: 27rpx; color: var(--text-sub); }
.eye.on { color: var(--primary); }
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
.check { width: 36rpx; height: 36rpx; border-radius: 18rpx; border: 1rpx solid var(--text-dim); margin-right: 14rpx; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.check.checked { background: var(--primary); border-color: var(--primary); }
.ck { color: #fff; font-size: 22rpx; }
.atext { color: var(--text-sub); font-size: 23rpx; flex: 1; line-height: 1.55; }
.alink { color: var(--primary); }
.btn-primary { background: var(--primary); color: #fff; text-align: center; padding: 27rpx 20rpx; border-radius: 16rpx; font-size: 30rpx; font-weight: 650; }
.btn-primary.disabled { opacity: 0.4; }
.security-note { display: block; text-align: center; color: var(--text-dim); font-size: 21rpx; margin: 20rpx 0 4rpx; }
</style>
