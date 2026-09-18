<template>
  <view class="page">
    <AppNavBar :title="t('phoneLoginSetupTitle')" />
    <scroll-view scroll-y class="body">
      <view class="card intro-card">
        <text class="eyebrow">{{ t('phoneLoginSetupKicker') }}</text>
        <text class="heading">{{ t('phoneLoginSetupTitle') }}</text>
        <text class="copy">{{ t('phoneLoginSetupHint') }}</text>
        <text class="notice">{{ t('phoneLoginUnverifiedNotice') }}</text>
      </view>

      <view class="card form-card">
        <view class="field">
          <text class="field-label">{{ t('phoneLoginIdentifier') }}</text>
          <input v-model="phone" class="field-input" type="number" maxlength="11" :placeholder="t('phoneLoginPlaceholder')" placeholder-class="placeholder" :disabled="submitting" />
        </view>
        <view class="field">
          <text class="field-label">{{ t('phoneLoginNewPassword') }}</text>
          <input v-model="password" class="field-input" :password="!showPassword" maxlength="64" :placeholder="t('phoneLoginPasswordPlaceholder')" placeholder-class="placeholder" :disabled="submitting" />
          <button class="show-password" @tap="showPassword = !showPassword">{{ t(showPassword ? 'hidePassword' : 'showPassword') }}</button>
        </view>
        <text class="password-hint">{{ t('phoneLoginPasswordHint') }}</text>
        <view v-if="requestError" class="request-error" role="alert">{{ requestError }}</view>
        <button class="submit" :loading="submitting" :disabled="!canSubmit" @tap="submit">{{ t(submitting ? 'phoneLoginSaving' : 'phoneLoginSave') }}</button>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onUnload } from '@dcloudio/uni-app'
import AppNavBar from '@/components/AppNavBar.vue'
import { configurePhoneLogin } from '@/api/user'
import { useI18nStore } from '@/store/i18n'

const { t, localizedErrorMessage } = useI18nStore()
const phone = ref('')
const password = ref('')
const showPassword = ref(false)
const submitting = ref(false)
const requestError = ref('')
const canSubmit = computed(() => /^1\d{10}$/.test(phone.value.trim()) && password.value.length >= 8 && password.value.length <= 64 && !submitting.value)
const ERROR_KEYS: Record<string, string> = {
  '该手机号已存在账号，请使用手机号登录后联系账号服务': 'phoneLoginConflict',
  '请在最近一次 KAI 登录后完成登录手机号设置': 'phoneLoginExpired',
}

function clearSensitiveFields() {
  password.value = ''
  showPassword.value = false
}

async function submit() {
  if (!canSubmit.value) {
    uni.showToast({ title: t('phoneLoginInvalid'), icon: 'none' })
    return
  }
  requestError.value = ''
  submitting.value = true
  const submittedPassword = password.value
  try {
    await configurePhoneLogin(phone.value.trim(), submittedPassword)
    clearSensitiveFields()
    uni.showModal({
      title: t('phoneLoginSavedTitle'),
      content: t('phoneLoginSavedMessage'),
      showCancel: false,
      confirmText: t('知道了'),
      success: () => uni.navigateBack(),
    })
  } catch (cause) {
    requestError.value = localizedErrorMessage(cause, 'phoneLoginFailed', ERROR_KEYS)
  } finally {
    submitting.value = false
  }
}

onHide(clearSensitiveFields)
onUnload(clearSensitiveFields)
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.body { flex: 1; box-sizing: border-box; padding: 24rpx 32rpx calc(64rpx + var(--safe-bottom)); }
.card { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); padding: 30rpx; }
.form-card { margin-top: 24rpx; }
.eyebrow { display: block; color: var(--primary); font-size: 19rpx; letter-spacing: 2rpx; }
.heading { display: block; margin-top: 10rpx; color: var(--text); font-size: 32rpx; font-weight: 650; }
.copy, .notice, .password-hint { display: block; margin-top: 18rpx; color: var(--text-sub); font-size: 24rpx; line-height: 1.65; }
.notice { padding: 18rpx; color: var(--text-sub); background: var(--bg); border-radius: 14rpx; }
.field { position: relative; margin-top: 30rpx; }
.field-label { display: block; margin-bottom: 12rpx; color: var(--text); font-size: 25rpx; }
.field-input { box-sizing: border-box; width: 100%; height: 88rpx; padding: 0 24rpx; color: var(--text); background: var(--bg); border: 1rpx solid var(--border); border-radius: 14rpx; font-size: 28rpx; }
.placeholder { color: var(--text-dim); }
.show-password { position: absolute; right: 12rpx; bottom: 13rpx; width: auto; padding: 10rpx 14rpx; color: var(--primary); background: transparent; font-size: 22rpx; line-height: 1.4; }
.show-password::after, .submit::after { border: none; }
.request-error { margin-top: 24rpx; padding: 20rpx; color: var(--down); background: var(--down-soft); border-radius: 14rpx; font-size: 24rpx; line-height: 1.55; }
.submit { margin-top: 28rpx; padding: 25rpx; color: #fff; background: var(--primary); border-radius: 16rpx; font-size: 28rpx; font-weight: 600; line-height: 1.4; }
.submit[disabled] { opacity: .45; }
</style>
