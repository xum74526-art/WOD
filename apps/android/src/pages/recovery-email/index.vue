<template>
  <view class="page">
    <AppNavBar :title="t('recoveryEmailTitle')" />
    <scroll-view scroll-y class="body">
      <view class="card status-card">
        <view class="status-heading">
          <view>
            <text class="eyebrow">EMAIL BINDING</text>
            <text class="heading">{{ t('recoveryEmailStatusTitle') }}</text>
          </view>
          <view v-if="status?.verified" class="status-badge verified">{{ t('recoveryEmailVerified') }}</view>
          <view v-else-if="!loading && !loadFailed" class="status-badge">{{ t('recoveryEmailNotBound') }}</view>
        </view>

        <text v-if="loading" class="status-copy muted">{{ t('recoveryEmailStatusLoading') }}</text>
        <template v-else-if="loadFailed">
          <text class="status-copy error-copy">{{ t('recoveryEmailLoadFailed') }}</text>
          <button class="retry" :disabled="loading" @tap="reloadPage">{{ t('recoveryEmailRetry') }}</button>
        </template>
        <text v-else-if="status?.verified && status.email" class="verified-email">{{ status.email }}</text>
        <text v-else class="status-copy muted">{{ t('recoveryEmailNotBoundHint') }}</text>
      </view>

      <view class="card form-card">
        <text class="heading">{{ t(status?.verified ? 'recoveryEmailChangeTitle' : 'recoveryEmailBindTitle') }}</text>
        <text class="form-hint">{{ t('recoveryEmailFormHint') }}</text>

        <view v-if="config?.email_enabled === false" class="service-notice" role="status">
          {{ t('recoveryEmailUnavailable') }}
        </view>
        <view v-else-if="configFailed" class="service-notice" role="status">
          <text class="service-copy">{{ t('recoveryEmailServiceUnknown') }}</text>
          <button class="retry service-retry" :disabled="loading" @tap="reloadPage">{{ t('recoveryEmailRetry') }}</button>
        </view>

        <view class="field">
          <text class="field-label">{{ t('recoveryEmailAddress') }}</text>
          <input
            v-model="email"
            class="field-input"
            type="text"
            inputmode="email"
            :maxlength="320"
            :disabled="submitting || !emailServiceEnabled"
            :placeholder="t('recoveryEmailAddressPlaceholder')"
            placeholder-class="placeholder"
          />
        </view>

        <view class="field">
          <text class="field-label">{{ t('recoveryEmailCurrentPassword') }}</text>
          <input
            v-model="currentPassword"
            class="field-input"
            password
            :maxlength="64"
            :disabled="submitting || !emailServiceEnabled"
            :placeholder="t('recoveryEmailPasswordPlaceholder')"
            placeholder-class="placeholder"
          />
        </view>

        <text class="verification-notice">{{ t('recoveryEmailVerificationNotice') }}</text>
        <view v-if="requestError" class="request-error" role="alert">{{ requestError }}</view>
        <button class="submit" :loading="submitting" :disabled="!canSubmit" @tap="submitVerification">
          {{ t(submitting ? 'recoveryEmailSending' : status?.verified ? 'recoveryEmailChangeAction' : 'recoveryEmailSendAction') }}
        </button>
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
  getRecoveryEmailStatus,
  requestRecoveryEmailVerification,
  type AccountRecoveryConfig,
  type RecoveryEmailStatus,
} from '@/api/account-recovery'
import { useI18nStore } from '@/store/i18n'

const { t } = useI18nStore()
const status = ref<RecoveryEmailStatus | null>(null)
const config = ref<AccountRecoveryConfig | null>(null)
const email = ref('')
const currentPassword = ref('')
const loading = ref(false)
const loadFailed = ref(false)
const configFailed = ref(false)
const submitting = ref(false)
const requestError = ref('')
const emailServiceEnabled = computed(() => config.value?.email_enabled === true)
const canSubmit = computed(() => emailServiceEnabled.value && !submitting.value && !!email.value.trim() && !!currentPassword.value)
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const REQUEST_ERROR_KEYS: Record<string, string> = {
  '当前密码错误': 'recoveryEmailErrorCurrentPassword',
  '邮箱找回服务尚未配置': 'recoveryEmailUnavailable',
  '邮箱服务尚未配置': 'recoveryEmailUnavailable',
  '找回请求参数无效，请检查后重试': 'recoveryEmailInvalidRequest',
  '请求过于频繁，请稍后再试': 'recoveryEmailTooFrequent',
}
let active = false
let pageGeneration = 0

function clearSensitiveFields() {
  email.value = ''
  currentPassword.value = ''
}

function requestErrorMessage(cause: unknown) {
  const source = cause instanceof Error ? cause.message : ''
  return t(REQUEST_ERROR_KEYS[source] || source || 'recoveryEmailRequestFailed')
}

async function refreshPage(generation: number) {
  loading.value = true
  loadFailed.value = false
  configFailed.value = false
  const [emailStatus, recoveryConfig] = await Promise.allSettled([
    getRecoveryEmailStatus(true),
    getAccountRecoveryConfig(),
  ])
  if (!active || generation !== pageGeneration) return
  if (emailStatus.status === 'fulfilled') status.value = emailStatus.value
  else {
    status.value = null
    loadFailed.value = true
  }
  if (recoveryConfig.status === 'fulfilled') config.value = recoveryConfig.value
  else {
    config.value = null
    configFailed.value = true
  }
  if (active && generation === pageGeneration) {
    loading.value = false
  }
}

function reloadPage() {
  if (loading.value) return
  const generation = ++pageGeneration
  void refreshPage(generation)
}

async function submitVerification() {
  if (!canSubmit.value) return
  const normalizedEmail = email.value.trim()
  if (normalizedEmail.length > 320 || !EMAIL_PATTERN.test(normalizedEmail)) {
    uni.showToast({ title: t('recoveryEmailInvalid'), icon: 'none' })
    return
  }

  const generation = pageGeneration
  const submittedPassword = currentPassword.value
  currentPassword.value = ''
  requestError.value = ''
  submitting.value = true
  try {
    const result = await requestRecoveryEmailVerification(normalizedEmail, submittedPassword)
    if (!active || generation !== pageGeneration) return
    clearSensitiveFields()
    uni.showModal({
      title: t(result.already_verified ? 'recoveryEmailAlreadyVerifiedTitle' : 'recoveryEmailSentTitle'),
      content: t(result.already_verified ? 'recoveryEmailAlreadyVerifiedMessage' : 'recoveryEmailSentMessage'),
      showCancel: false,
      confirmText: t('知道了'),
    })
    void refreshPage(generation)
  } catch (cause) {
    if (active && generation === pageGeneration) requestError.value = requestErrorMessage(cause)
  } finally {
    if (generation === pageGeneration) submitting.value = false
  }
}

function leavePage() {
  active = false
  pageGeneration += 1
  loading.value = false
  submitting.value = false
  status.value = null
  config.value = null
  loadFailed.value = false
  configFailed.value = false
  requestError.value = ''
  clearSensitiveFields()
}

onShow(() => {
  active = true
  reloadPage()
})
onHide(leavePage)
onUnload(leavePage)
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.body { flex: 1; box-sizing: border-box; padding: 24rpx 32rpx calc(64rpx + var(--safe-bottom)); }
.card { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }
.status-card, .form-card { padding: 30rpx; }
.form-card { margin-top: 24rpx; }
.status-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 20rpx; }
.eyebrow { display: block; margin-bottom: 8rpx; color: var(--primary); font-size: 19rpx; letter-spacing: 2rpx; }
.heading { display: block; color: var(--text); font-size: 31rpx; font-weight: 650; }
.status-badge { flex: none; padding: 8rpx 16rpx; border-radius: 999rpx; color: var(--text-sub); background: var(--bg); font-size: 21rpx; }
.status-badge.verified { color: var(--up); background: var(--up-soft); }
.status-copy, .verified-email { display: block; margin-top: 24rpx; font-size: 28rpx; line-height: 1.55; }
.verified-email { color: var(--text); font-weight: 600; word-break: break-all; }
.muted, .form-hint, .verification-notice { color: var(--text-sub); }
.error-copy { color: var(--down); }
.retry { width: auto; margin: 20rpx 0 0; padding: 12rpx 24rpx; color: var(--primary); background: var(--primary-soft); border-radius: 999rpx; font-size: 24rpx; line-height: 1.4; }
.retry::after, .submit::after { border: none; }
.form-hint { display: block; margin-top: 14rpx; font-size: 24rpx; line-height: 1.6; }
.service-notice, .request-error { margin-top: 22rpx; padding: 20rpx 22rpx; border-radius: 14rpx; font-size: 24rpx; line-height: 1.55; }
.service-notice { color: var(--text-sub); background: var(--bg); border: 1rpx solid var(--border); }
.service-copy { display: block; }
.service-retry { margin-top: 14rpx; }
.request-error { color: var(--down); background: var(--down-soft); }
.field { margin-top: 30rpx; }
.field-label { display: block; margin-bottom: 12rpx; color: var(--text); font-size: 25rpx; }
.field-input { box-sizing: border-box; width: 100%; height: 88rpx; padding: 0 24rpx; color: var(--text); background: var(--bg); border: 1rpx solid var(--border); border-radius: 14rpx; font-size: 28rpx; }
.placeholder { color: var(--text-dim); }
.verification-notice { display: block; margin-top: 24rpx; font-size: 23rpx; line-height: 1.65; }
.submit { margin-top: 28rpx; padding: 25rpx; color: #fff; background: var(--primary); border-radius: 16rpx; font-size: 28rpx; font-weight: 600; line-height: 1.4; }
.submit[disabled] { opacity: .45; }
</style>
