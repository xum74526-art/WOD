<template>
  <view class="page">
    <AppNavBar :title="t('passwordResetTitle')" />
    <scroll-view scroll-y class="body">
      <view class="card intro-card">
        <text class="eyebrow">SECURE PASSWORD RESET</text>
        <text class="heading">{{ t('passwordResetTitle') }}</text>
        <text class="description">{{ t('passwordResetDescription') }}</text>
      </view>

      <view class="card form-card">
        <view class="field">
          <text class="field-label">{{ t('passwordResetCode') }}</text>
          <input
            v-model="token"
            class="field-input code-input"
            type="text"
            :maxlength="256"
            :disabled="submitting"
            :placeholder="t('passwordResetCodePlaceholder')"
            placeholder-class="placeholder"
          />
        </view>
        <view class="field">
          <text class="field-label">{{ t('passwordResetNewPassword') }}</text>
          <input
            v-model="password"
            class="field-input"
            password
            :maxlength="64"
            :disabled="submitting"
            :placeholder="t('passwordResetNewPasswordPlaceholder')"
            placeholder-class="placeholder"
          />
        </view>
        <view class="field">
          <text class="field-label">{{ t('passwordResetConfirmPassword') }}</text>
          <input
            v-model="confirmation"
            class="field-input"
            password
            :maxlength="64"
            :disabled="submitting"
            :placeholder="t('passwordResetConfirmPasswordPlaceholder')"
            placeholder-class="placeholder"
          />
        </view>
        <text class="security-notice">{{ t('passwordResetSecurityNotice') }}</text>
        <view v-if="requestError" class="request-error" role="alert">{{ requestError }}</view>
        <button class="submit" :loading="submitting" :disabled="!canSubmit" @tap="submitReset">
          {{ t(submitting ? 'passwordResetSubmitting' : 'passwordResetSubmit') }}
        </button>
        <button class="back-link" @tap="requestAgain">{{ t('passwordResetRequestAgain') }}</button>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import AppNavBar from '@/components/AppNavBar.vue'
import { confirmPasswordReset } from '@/api/account-recovery'
import { useI18nStore } from '@/store/i18n'
import { takePendingPasswordResetToken } from '@/utils/password-reset-callback'

const { t } = useI18nStore()
const token = ref('')
const password = ref('')
const confirmation = ref('')
const submitting = ref(false)
const requestError = ref('')
const normalizedToken = computed(() => token.value.trim())
const hasValidToken = computed(() => normalizedToken.value.length >= 32 && normalizedToken.value.length <= 256)
const canSubmit = computed(() => hasValidToken.value && !submitting.value && !!password.value && !!confirmation.value)
const REQUEST_ERROR_KEYS: Record<string, string> = {
  '链接无效或已过期，请重新申请': 'passwordResetInvalidToken',
  '找回请求参数无效，请检查后重试': 'passwordRecoveryInvalidRequest',
  '请求过于频繁，请稍后再试': 'passwordRecoveryTooFrequent',
}
let active = false
let pageGeneration = 0

function takePendingToken() {
  const candidate = takePendingPasswordResetToken().trim()
  if (!candidate) return
  token.value = candidate.length >= 32 && candidate.length <= 256 ? candidate : ''
  password.value = ''
  confirmation.value = ''
  requestError.value = ''
}

function clearSensitiveFields() {
  token.value = ''
  password.value = ''
  confirmation.value = ''
}

function requestErrorMessage(cause: unknown) {
  const source = cause instanceof Error ? cause.message : ''
  return t(REQUEST_ERROR_KEYS[source] || source || 'passwordResetFailed')
}

async function submitReset() {
  if (!canSubmit.value) return
  if (password.value.length < 8 || password.value.length > 64) {
    uni.showToast({ title: t('passwordResetPasswordLength'), icon: 'none' })
    return
  }
  if (password.value !== confirmation.value) {
    uni.showToast({ title: t('passwordResetPasswordMismatch'), icon: 'none' })
    return
  }

  const generation = pageGeneration
  const submittedToken = normalizedToken.value
  const submittedPassword = password.value
  password.value = ''
  confirmation.value = ''
  requestError.value = ''
  submitting.value = true
  try {
    await confirmPasswordReset(submittedToken, submittedPassword)
    if (!active || generation !== pageGeneration) return
    clearSensitiveFields()
    uni.showModal({
      title: t('passwordResetSuccessTitle'),
      content: t('passwordResetSuccessMessage'),
      showCancel: false,
      confirmText: t('passwordRecoveryBackLogin'),
      complete: () => uni.reLaunch({ url: '/pages/login/index' }),
    })
  } catch (cause) {
    if (!active || generation !== pageGeneration) return
    const source = cause instanceof Error ? cause.message : ''
    if (source === '链接无效或已过期，请重新申请') token.value = ''
    requestError.value = requestErrorMessage(cause)
  } finally {
    if (active && generation === pageGeneration) submitting.value = false
  }
}

function requestAgain() {
  clearSensitiveFields()
  uni.redirectTo({ url: '/pages/forgot-password/index' })
}

function leavePage() {
  active = false
  pageGeneration += 1
  submitting.value = false
  requestError.value = ''
  clearSensitiveFields()
}

onLoad(() => {
  uni.$on('wod-password-reset-token-ready', takePendingToken)
  takePendingToken()
})
onShow(() => {
  active = true
  takePendingToken()
})
onUnload(() => {
  uni.$off('wod-password-reset-token-ready', takePendingToken)
  leavePage()
})
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.body { flex: 1; box-sizing: border-box; padding: 24rpx 32rpx calc(64rpx + var(--safe-bottom)); }
.card { padding: 30rpx; background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }
.form-card { margin-top: 24rpx; }
.eyebrow { display: block; margin-bottom: 8rpx; color: var(--primary); font-size: 19rpx; letter-spacing: 2rpx; }
.heading { display: block; color: var(--text); font-size: 31rpx; font-weight: 650; }
.description { display: block; margin-top: 14rpx; color: var(--text-sub); font-size: 24rpx; line-height: 1.65; }
.centered { text-align: center; }
.field + .field { margin-top: 28rpx; }
.field-label { display: block; margin-bottom: 12rpx; color: var(--text); font-size: 25rpx; }
.field-input { box-sizing: border-box; width: 100%; height: 88rpx; padding: 0 24rpx; color: var(--text); background: var(--bg); border: 1rpx solid var(--border); border-radius: 14rpx; font-size: 28rpx; }
.code-input { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 25rpx; }
.placeholder { color: var(--text-dim); }
.security-notice { display: block; margin-top: 24rpx; color: var(--text-sub); font-size: 23rpx; line-height: 1.65; }
.request-error { margin-top: 24rpx; padding: 20rpx 22rpx; color: var(--down); background: var(--down-soft); border-radius: 14rpx; font-size: 24rpx; line-height: 1.55; }
.submit { margin-top: 28rpx; padding: 25rpx; color: #fff; background: var(--primary); border-radius: 16rpx; font-size: 28rpx; font-weight: 600; line-height: 1.4; }
.submit::after { border: none; }
.submit[disabled] { opacity: .45; }
.back-link { width: auto; margin: 22rpx auto 0; padding: 8rpx; color: var(--primary); background: transparent; font-size: 24rpx; line-height: 1.4; }
.back-link::after { border: none; }
</style>
