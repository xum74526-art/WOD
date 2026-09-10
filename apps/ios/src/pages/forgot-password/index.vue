<template>
  <view class="page">
    <AppNavBar :title="t('passwordRecoveryTitle')" />
    <scroll-view scroll-y class="body">
      <view class="card intro-card">
        <text class="eyebrow">{{ t('passwordRecoveryKicker') }}</text>
        <text class="heading">{{ t('passwordRecoveryTitle') }}</text>
        <text class="description">{{ t('passwordRecoveryDescription') }}</text>
      </view>

      <view v-if="sent" class="card result-card" role="status">
        <view class="result-mark">✓</view>
        <text class="heading centered">{{ t('passwordRecoveryEmailSentTitle') }}</text>
        <text class="description centered">{{ t('passwordRecoveryEmailSentMessage') }}</text>
        <button class="submit" @tap="openResetPage">{{ t('passwordRecoveryEnterCode') }}</button>
        <button class="back-link" @tap="backToLogin">{{ t('passwordRecoveryBackLogin') }}</button>
      </view>

      <view v-else class="card form-card">
        <view v-if="config?.email_enabled === false" class="service-notice" role="status">
          {{ t('passwordRecoveryUnavailable') }}
        </view>
        <view v-else-if="configFailed" class="service-notice" role="status">
          <text class="service-copy">{{ t('passwordRecoveryServiceUnknown') }}</text>
          <button class="retry" :disabled="loading" @tap="loadConfig">{{ t('passwordRecoveryRetry') }}</button>
        </view>

        <view class="field">
          <text class="field-label">{{ t('passwordRecoveryEmailLabel') }}</text>
          <input
            v-model="email"
            class="field-input"
            type="text"
            inputmode="email"
            :maxlength="320"
            :disabled="submitting || !emailServiceEnabled"
            :placeholder="t('passwordRecoveryEmailPlaceholder')"
            placeholder-class="placeholder"
          />
        </view>
        <text class="privacy-notice">{{ t('passwordRecoveryPrivacyNotice') }}</text>
        <view v-if="requestError" class="request-error" role="alert">{{ requestError }}</view>
        <button class="submit" :loading="submitting" :disabled="!canSubmit" @tap="submitRequest">
          {{ t(submitting ? 'passwordRecoverySending' : 'passwordRecoverySend') }}
        </button>
        <button class="back-link" @tap="openResetPage">{{ t('passwordRecoveryHaveCode') }}</button>
        <button class="back-link" @tap="backToLogin">{{ t('passwordRecoveryBackLogin') }}</button>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onShow, onUnload } from '@dcloudio/uni-app'
import AppNavBar from '@/components/AppNavBar.vue'
import {
  getAccountRecoveryConfig,
  requestPasswordReset,
  type AccountRecoveryConfig,
} from '@/api/account-recovery'
import { useI18nStore } from '@/store/i18n'

const { t, localizedErrorMessage } = useI18nStore()
const config = ref<AccountRecoveryConfig | null>(null)
const email = ref('')
const loading = ref(false)
const configFailed = ref(false)
const submitting = ref(false)
const sent = ref(false)
const requestError = ref('')
const emailServiceEnabled = computed(() => config.value?.email_enabled === true)
const canSubmit = computed(() => emailServiceEnabled.value && !submitting.value && !!email.value.trim())
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const REQUEST_ERROR_KEYS: Record<string, string> = {
  '邮箱找回服务尚未配置': 'passwordRecoveryUnavailable',
  '邮箱服务尚未配置': 'passwordRecoveryUnavailable',
  '找回请求参数无效，请检查后重试': 'passwordRecoveryInvalidRequest',
  '请求过于频繁，请稍后再试': 'passwordRecoveryTooFrequent',
}
let active = false
let pageGeneration = 0

function requestErrorMessage(cause: unknown) {
  return localizedErrorMessage(cause, 'passwordRecoveryRequestFailed', REQUEST_ERROR_KEYS)
}

async function loadConfig() {
  if (loading.value) return
  const generation = ++pageGeneration
  loading.value = true
  configFailed.value = false
  requestError.value = ''
  try {
    const result = await getAccountRecoveryConfig()
    if (!active || generation !== pageGeneration) return
    config.value = result
  } catch {
    if (!active || generation !== pageGeneration) return
    config.value = null
    configFailed.value = true
  } finally {
    if (active && generation === pageGeneration) loading.value = false
  }
}

async function submitRequest() {
  if (!canSubmit.value) return
  const normalizedEmail = email.value.trim()
  if (normalizedEmail.length > 320 || !EMAIL_PATTERN.test(normalizedEmail)) {
    uni.showToast({ title: t('passwordRecoveryInvalidEmail'), icon: 'none' })
    return
  }

  const generation = pageGeneration
  requestError.value = ''
  submitting.value = true
  try {
    await requestPasswordReset(normalizedEmail)
    if (!active || generation !== pageGeneration) return
    email.value = ''
    sent.value = true
  } catch (cause) {
    if (active && generation === pageGeneration) requestError.value = requestErrorMessage(cause)
  } finally {
    if (active && generation === pageGeneration) submitting.value = false
  }
}

function backToLogin() {
  uni.reLaunch({ url: '/pages/login/index' })
}

function openResetPage() {
  uni.navigateTo({ url: '/pages/reset-password/index' })
}

function leavePage() {
  active = false
  pageGeneration += 1
  email.value = ''
  requestError.value = ''
  submitting.value = false
  loading.value = false
}

onShow(() => {
  active = true
  if (!config.value && !sent.value) void loadConfig()
})
onHide(leavePage)
onUnload(leavePage)
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.body { flex: 1; box-sizing: border-box; padding: 24rpx 32rpx calc(64rpx + var(--safe-bottom)); }
.card { padding: 30rpx; background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }
.form-card, .result-card { margin-top: 24rpx; }
.eyebrow { display: block; margin-bottom: 8rpx; color: var(--primary); font-size: 19rpx; letter-spacing: 2rpx; }
.heading { display: block; color: var(--text); font-size: 31rpx; font-weight: 650; }
.description { display: block; margin-top: 14rpx; color: var(--text-sub); font-size: 24rpx; line-height: 1.65; }
.centered { text-align: center; }
.service-notice, .request-error { margin-bottom: 26rpx; padding: 20rpx 22rpx; border-radius: 14rpx; font-size: 24rpx; line-height: 1.55; }
.service-notice { color: var(--text-sub); background: var(--bg); border: 1rpx solid var(--border); }
.service-copy { display: block; }
.request-error { color: var(--down); background: var(--down-soft); }
.retry { width: auto; margin: 14rpx 0 0; padding: 12rpx 24rpx; color: var(--primary); background: var(--primary-soft); border-radius: 999rpx; font-size: 24rpx; line-height: 1.4; }
.retry::after, .submit::after, .back-link::after { border: none; }
.field-label { display: block; margin-bottom: 12rpx; color: var(--text); font-size: 25rpx; }
.field-input { box-sizing: border-box; width: 100%; height: 88rpx; padding: 0 24rpx; color: var(--text); background: var(--bg); border: 1rpx solid var(--border); border-radius: 14rpx; font-size: 28rpx; }
.placeholder { color: var(--text-dim); }
.privacy-notice { display: block; margin-top: 24rpx; color: var(--text-sub); font-size: 23rpx; line-height: 1.65; }
.submit { margin-top: 28rpx; padding: 25rpx; color: #fff; background: var(--primary); border-radius: 16rpx; font-size: 28rpx; font-weight: 600; line-height: 1.4; }
.submit[disabled] { opacity: .45; }
.back-link { width: auto; margin: 22rpx auto 0; padding: 8rpx; color: var(--primary); background: transparent; font-size: 24rpx; line-height: 1.4; }
.result-card { padding-top: 44rpx; padding-bottom: 44rpx; }
.result-mark { width: 76rpx; height: 76rpx; margin: 0 auto 24rpx; display: flex; align-items: center; justify-content: center; color: #fff; background: var(--up); border-radius: 50%; font-size: 40rpx; font-weight: 700; }
</style>
