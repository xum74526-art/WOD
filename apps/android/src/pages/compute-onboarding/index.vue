<template>
  <view class="page">
    <AppNavBar :title="t('deviceHosting')" />
    <view class="shell">
      <view class="intro">
        <view class="intro-icon"><AppIcon name="device" :size="46" /></view>
        <view class="intro-copy">
          <text class="intro-title">{{ t('deviceHosting') }}</text>
          <text class="intro-description">{{ t('hostingSummary') }}</text>
        </view>
      </view>

      <view v-if="!canSubmit" class="card verification-gate">
        <view class="gate-icon"><AppIcon name="verified" :size="44" /></view>
        <text class="gate-title">{{ t('hostingEligibility') }}</text>
        <text class="gate-description">{{ t('verifyBeforeHosting') }}</text>
        <view class="gate-action" @tap="goVerify">{{ t('verifyNow') }}</view>
      </view>

      <template v-else>
        <SectionHeader :title="t('k_4fad0d62')" />
        <view class="card form">
          <view class="field">
            <text class="field-label">{{ t('k_7140ad6a') }}</text>
            <view class="seg-mini">
              <text class="seg-item active">{{ t(hostingStore.isApprovedMerchant ? 'k_04c9e3ab' : 'k_6a0e0419') }}</text>
            </view>
          </view>
          <view class="field">
            <text class="field-label">{{ t('k_52409da5') }}</text>
            <input class="field-input" v-model="form.contact" :placeholder="t('k_60d0458a')" placeholder-class="input-placeholder" />
          </view>
          <view class="field">
            <text class="field-label">{{ t('k_09a1f698') }}</text>
            <input class="field-input" v-model="form.phone" type="number" :placeholder="t('k_8098e2b4')" placeholder-class="input-placeholder" maxlength="11" />
          </view>
          <view class="field">
            <text class="field-label">{{ t('k_5858832b') }}</text>
            <input class="field-input" v-model="form.device_model" :placeholder="t('k_3d0ba34f')" placeholder-class="input-placeholder" />
          </view>
          <view class="field">
            <text class="field-label">{{ t('k_74739b03') }}</text>
            <input class="field-input" v-model="form.device_count" type="number" :placeholder="t('k_06ac2d16')" placeholder-class="input-placeholder" />
          </view>
          <view class="field">
            <text class="field-label">{{ t('k_39879623') }}</text>
            <input class="field-input" v-model="form.location" :placeholder="t('k_97a15217')" placeholder-class="input-placeholder" />
          </view>
          <view class="field">
            <text class="field-label">{{ t('k_2432b575') }}</text>
            <input class="field-input" v-model="form.remark" :placeholder="t('k_93a4386c')" placeholder-class="input-placeholder" />
          </view>
          <view class="submit-button" :class="{ disabled: submitting }" @tap="onSubmit">
            {{ t(submitting ? '提交中...' : '提交申请') }}
          </view>
        </view>
      </template>

      <SectionHeader :title="t('applicationHistory')" />
      <view v-if="hostingStore.loading && !hostingStore.lastUpdated" class="card history-skeleton"></view>
      <view v-else-if="!hostingStore.applications.length" class="card empty-history">
        <text>{{ t('noHostingDevices') }}</text>
      </view>
      <view v-for="item in hostingStore.applications" :key="item.id" class="card history-row">
        <view class="history-head">
          <view class="history-name-wrap">
            <text class="history-name">{{ item.device_model }}</text>
            <text class="history-count">{{ t('countDevices', { count: item.device_count }) }}</text>
          </view>
          <StatusBadge :text="applicationStatusLabel(item.status)" :type="applicationBadgeType(item.status)" />
        </view>
        <text class="history-description">{{ applicationDescription(item.status) }}</text>
        <view class="history-meta">
          <text>#{{ item.id }}</text>
          <text v-if="item.created_at">{{ t('submittedAt') }} {{ formatDate(item.created_at) }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { submitOnboarding } from '@/api/onboarding'
import AppIcon from '@/components/AppIcon.vue'
import AppNavBar from '@/components/AppNavBar.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useHostingStore } from '@/store/hosting'
import { useI18nStore } from '@/store/i18n'
import { formatDate } from '@/utils/format'
import { navigateTo as nav } from '@/utils/nav'

const hostingStore = useHostingStore()
const { t } = useI18nStore()
const submitting = ref(false)
const form = reactive({
  entity_type: 'personal' as 'personal' | 'company',
  contact: '',
  phone: '',
  device_model: '',
  device_count: '1',
  location: '',
  remark: '',
})

const canSubmit = computed(() => hostingStore.isApprovedMerchant || hostingStore.verification?.status === 'verified')

function applicationStatusLabel(status: string) {
  if (status === 'contacted') return t('underReview')
  if (status === 'approved') return t('deploying')
  if (status === 'rejected') return t('actionRequired')
  return t('pendingReview')
}

function applicationDescription(status: string) {
  if (status === 'contacted') return t('applicationContacted')
  if (status === 'approved') return t('applicationApproved')
  if (status === 'rejected') return t('applicationRejected')
  return t('applicationSubmitted')
}

function applicationBadgeType(status: string): 'default' | 'down' {
  return status === 'rejected' ? 'down' : 'default'
}

async function onSubmit() {
  if (submitting.value || !canSubmit.value) return
  if (!form.contact || !form.phone || !form.device_model) {
    uni.showToast({ title: t('请填完整'), icon: 'none' })
    return
  }
  if (Number(form.device_count) <= 0) {
    uni.showToast({ title: t('deviceCountPositive'), icon: 'none' })
    return
  }
  submitting.value = true
  try {
    form.entity_type = hostingStore.isApprovedMerchant ? 'company' : 'personal'
    await submitOnboarding({ ...form, device_count: Number(form.device_count) })
    uni.showToast({ title: t('提交成功'), icon: 'success' })
    form.device_model = ''
    form.device_count = '1'
    form.location = ''
    form.remark = ''
    await hostingStore.refresh()
  } catch {}
  submitting.value = false
}

function goVerify() { nav('/pages/verification/index') }

onShow(() => hostingStore.refresh())
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; min-height: 100dvh; background: var(--bg); }
.shell { padding: 8rpx 32rpx calc(132rpx + var(--safe-bottom)); }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--card-border); box-shadow: var(--shadow); }
.intro { display: flex; align-items: center; gap: 20rpx; padding: 28rpx 0 18rpx; }
.intro-icon { width: 78rpx; height: 78rpx; border-radius: 20rpx; background: var(--primary-soft); color: var(--primary); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.intro-copy { min-width: 0; }
.intro-title { display: block; color: var(--text); font-size: 34rpx; font-weight: 720; }
.intro-description { display: block; color: var(--text-sub); font-size: 23rpx; line-height: 1.45; margin-top: 6rpx; }
.verification-gate { padding: 38rpx 32rpx; margin: 22rpx 0; text-align: center; }
.gate-icon { width: 84rpx; height: 84rpx; margin: 0 auto 18rpx; border-radius: 21rpx; background: var(--primary-soft); color: var(--primary); display: flex; align-items: center; justify-content: center; }
.gate-title { display: block; color: var(--text); font-size: 31rpx; font-weight: 700; }
.gate-description { display: block; color: var(--text-sub); font-size: 24rpx; line-height: 1.55; margin-top: 10rpx; }
.gate-action { min-height: 78rpx; border-radius: 18rpx; margin-top: 28rpx; background: var(--primary); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 26rpx; font-weight: 650; }
.form { padding: 24rpx 30rpx 30rpx; }
.field { margin-bottom: 28rpx; }
.field-label { color: var(--text-sub); font-size: 23rpx; display: block; margin-bottom: 12rpx; }
.field-input { width: 100%; box-sizing: border-box; min-height: 72rpx; color: var(--text); font-size: 29rpx; border-bottom: 1rpx solid var(--divider); }
.input-placeholder { color: var(--text-dim); }
.seg-mini { display: flex; }
.seg-item { min-width: 180rpx; text-align: center; padding: 18rpx 24rpx; border: 1rpx solid var(--primary); border-radius: 16rpx; color: var(--primary); background: var(--primary-soft); font-size: 26rpx; }
.submit-button { min-height: 84rpx; background: var(--primary); color: #fff; display: flex; align-items: center; justify-content: center; border-radius: 18rpx; font-size: 28rpx; font-weight: 650; }
.submit-button:active, .gate-action:active { transform: scale(0.99); }
.submit-button.disabled { opacity: 0.45; }
.history-row { padding: 28rpx; margin-bottom: 16rpx; }
.history-head { display: flex; align-items: center; justify-content: space-between; gap: 18rpx; }
.history-name-wrap { min-width: 0; }
.history-name { color: var(--text); font-size: 29rpx; font-weight: 680; }
.history-count { color: var(--text-sub); font-size: 22rpx; margin-left: 12rpx; }
.history-description { display: block; color: var(--text-sub); font-size: 23rpx; line-height: 1.5; margin-top: 16rpx; }
.history-meta { display: flex; justify-content: space-between; color: var(--text-dim); font-size: 20rpx; margin-top: 16rpx; padding-top: 16rpx; border-top: 1rpx solid var(--divider); }
.empty-history { padding: 44rpx; color: var(--text-sub); text-align: center; font-size: 24rpx; }
.history-skeleton { height: 176rpx; background: linear-gradient(90deg, var(--card), var(--bg-2), var(--card)); background-size: 200% 100%; animation: skeleton-shift 1.2s ease infinite; }
@keyframes skeleton-shift { from { background-position: 100% 0; } to { background-position: -100% 0; } }
@media (prefers-reduced-motion: reduce) {
  .history-skeleton { animation: none; }
  .submit-button, .gate-action { transition: none; }
}
</style>
