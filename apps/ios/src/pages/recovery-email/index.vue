<template>
  <view class="page">
    <AppNavBar :title="t('recoveryEmail')" />
    <scroll-view scroll-y class="body">
      <view class="card status-card">
        <view class="status-head">
          <text class="status-label">{{ t('recoveryEmailCurrent') }}</text>
          <text class="status-badge" :class="{ verified: status?.verified }">
            {{ t(status?.verified ? 'recoveryEmailBound' : 'recoveryEmailUnbound') }}
          </text>
        </view>
        <text class="status-value">{{ status?.email || t('recoveryEmailNotSet') }}</text>
        <text class="status-hint">{{ t('recoveryEmailStatusHint') }}</text>
        <view v-if="loadFailed" class="load-error" @tap="loadStatus">
          <text>{{ t('recoveryEmailLoadFailed') }}</text>
          <text class="retry">{{ t('refresh') }}</text>
        </view>
      </view>

      <SectionHeader :title="t(status?.verified ? 'recoveryEmailReplaceTitle' : 'recoveryEmailBindTitle')" />
      <view class="card form-card">
        <view v-if="emailEnabled === false" class="unavailable">
          <text class="unavailable-title">{{ t('recoveryEmailUnavailable') }}</text>
          <text class="unavailable-hint">{{ t('recoveryEmailUnavailableHint') }}</text>
        </view>
        <view class="field">
          <text class="field-label">{{ t('recoveryEmailAddressLabel') }}</text>
          <input
            v-model="form.email"
            class="field-input"
            type="text"
            :maxlength="320"
            :disabled="emailEnabled !== true"
            :placeholder="t('recoveryEmailAddressPlaceholder')"
            placeholder-class="placeholder"
          />
        </view>
        <view class="field">
          <text class="field-label">{{ t('recoveryEmailPasswordLabel') }}</text>
          <input
            v-model="form.currentPassword"
            class="field-input"
            type="text"
            :password="true"
            :maxlength="64"
            :disabled="emailEnabled !== true"
            :placeholder="t('recoveryEmailPasswordPlaceholder')"
            placeholder-class="placeholder"
          />
        </view>
        <view class="submit" :class="{ disabled: submitting || emailEnabled !== true }" @tap="submit">
          {{ t(submitting ? 'recoveryEmailSubmitting' : 'recoveryEmailSubmit') }}
        </view>
        <text class="privacy-hint">{{ t('recoveryEmailPrivacyHint') }}</text>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { onUnmounted, reactive, ref } from 'vue'
import { onHide, onShow } from '@dcloudio/uni-app'
import {
  getAccountRecoveryConfig,
  getRecoveryEmailStatus,
  requestRecoveryEmailVerification,
  type RecoveryEmailStatus,
} from '@/api/user'
import AppNavBar from '@/components/AppNavBar.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import { useI18nStore } from '@/store/i18n'

const { t } = useI18nStore()
const status = ref<RecoveryEmailStatus | null>(null)
const loadFailed = ref(false)
const loading = ref(false)
const submitting = ref(false)
const emailEnabled = ref<boolean | null>(null)
const form = reactive({ email: '', currentPassword: '' })
let active = false
let loadGeneration = 0
let submitGeneration = 0

const submitErrorKeys: Record<string, string> = {
  '当前密码错误': 'recoveryEmailPasswordIncorrect',
  'Current password is incorrect': 'recoveryEmailPasswordIncorrect',
  '邮箱找回服务尚未配置': 'recoveryEmailUnavailable',
  '邮箱服务尚未配置': 'recoveryEmailUnavailable',
  'Email binding is unavailable': 'recoveryEmailUnavailable',
  '找回请求参数无效，请检查后重试': 'recoveryEmailRequestInvalid',
  'The recovery request is invalid. Check the information and try again.': 'recoveryEmailRequestInvalid',
  '请求过于频繁，请稍后再试': 'recoveryEmailTooFrequent',
  'Too many requests. Please try again later.': 'recoveryEmailTooFrequent',
}

function validEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
}

async function loadStatus() {
  if (loading.value) return
  const generation = ++loadGeneration
  loading.value = true
  loadFailed.value = false
  try {
    const [configResult, statusResult] = await Promise.allSettled([
      getAccountRecoveryConfig(),
      getRecoveryEmailStatus(true),
    ])
    if (!active || generation !== loadGeneration) return
    emailEnabled.value = configResult.status === 'fulfilled'
      ? configResult.value.email_enabled
      : false
    if (statusResult.status === 'fulfilled') {
      status.value = statusResult.value
    } else {
      loadFailed.value = true
    }
    if (configResult.status === 'rejected') loadFailed.value = true
  } finally {
    if (active && generation === loadGeneration) loading.value = false
  }
}

onShow(() => {
  active = true
  void loadStatus()
})
onHide(() => {
  active = false
  loadGeneration += 1
  submitGeneration += 1
  loading.value = false
  submitting.value = false
  form.email = ''
  form.currentPassword = ''
})

async function submit() {
  if (submitting.value) return
  if (emailEnabled.value !== true) {
    uni.showToast({ title: t('recoveryEmailUnavailable'), icon: 'none' })
    return
  }
  const email = form.email.trim()
  if (!validEmail(email)) {
    uni.showToast({ title: t('recoveryEmailInvalid'), icon: 'none' })
    return
  }
  if (!form.currentPassword) {
    uni.showToast({ title: t('recoveryEmailPasswordPlaceholder'), icon: 'none' })
    return
  }
  const generation = ++submitGeneration
  submitting.value = true
  try {
    const result = await requestRecoveryEmailVerification(email, form.currentPassword)
    if (!active || generation !== submitGeneration) return
    form.email = ''
    const alreadyVerified = result.already_verified
    uni.showModal({
      title: t(alreadyVerified ? 'recoveryEmailAlreadyVerifiedTitle' : 'recoveryEmailSentTitle'),
      content: t(alreadyVerified ? 'recoveryEmailAlreadyVerifiedHint' : 'recoveryEmailSentHint'),
      showCancel: false,
      confirmText: t('知道了'),
    })
    if (alreadyVerified) await loadStatus()
  } catch (error) {
    if (!active || generation !== submitGeneration) return
    const message = error instanceof Error ? error.message : ''
    const key = submitErrorKeys[message]
    uni.showToast({ title: key ? t(key) : (message || t('请求失败')), icon: 'none' })
  } finally {
    if (generation === submitGeneration) {
      form.currentPassword = ''
      submitting.value = false
    }
  }
}

onUnmounted(() => {
  active = false
  loadGeneration += 1
  submitGeneration += 1
  submitting.value = false
  form.email = ''
  form.currentPassword = ''
})
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.body { flex: 1; padding: 24rpx 32rpx calc(132rpx + var(--safe-bottom)); box-sizing: border-box; }
.card { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }
.status-card { padding: 32rpx; }
.status-head { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; }
.status-label { color: var(--text-sub); font-size: 24rpx; }
.status-badge { flex-shrink: 0; padding: 7rpx 16rpx; color: var(--text-sub); background: var(--bg-2); border-radius: 999rpx; font-size: 20rpx; }
.status-badge.verified { color: var(--up); background: var(--up-soft); }
.status-value { display: block; margin-top: 18rpx; color: var(--text); font-size: 32rpx; font-weight: 700; word-break: break-all; }
.status-hint { display: block; margin-top: 12rpx; color: var(--text-sub); font-size: 22rpx; line-height: 1.55; }
.load-error { display: flex; justify-content: space-between; gap: 20rpx; margin-top: 20rpx; padding-top: 20rpx; border-top: 1rpx solid var(--divider); color: var(--text-sub); font-size: 22rpx; }
.retry { flex-shrink: 0; color: var(--primary); font-weight: 700; }
.form-card { padding: 16rpx 32rpx 30rpx; }
.unavailable { margin: 16rpx 0 4rpx; padding: 22rpx 24rpx; border-radius: 18rpx; background: var(--bg-2); }
.unavailable-title { display: block; color: var(--text); font-size: 24rpx; font-weight: 700; }
.unavailable-hint { display: block; margin-top: 7rpx; color: var(--text-sub); font-size: 21rpx; line-height: 1.5; }
.field { padding: 26rpx 0; border-bottom: 1rpx solid var(--divider); }
.field-label { display: block; margin-bottom: 12rpx; color: var(--text-sub); font-size: 24rpx; }
.field-input { color: var(--text); font-size: 30rpx; line-height: 48rpx; }
.placeholder { color: var(--text-dim); }
.submit { margin-top: 32rpx; padding: 27rpx 24rpx; border-radius: var(--radius); background: var(--primary); color: #fff; text-align: center; font-size: 29rpx; font-weight: 700; }
.submit.disabled { opacity: .45; }
.privacy-hint { display: block; margin-top: 18rpx; color: var(--text-dim); font-size: 21rpx; line-height: 1.55; text-align: center; }
</style>
