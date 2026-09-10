<template>
  <view class="page">
    <AppNavBar :title="t('merchantJoin')" />
    <view class="shell">
      <view class="intro">
        <view class="intro-icon"><AppIcon name="gpu" :size="44" /></view>
        <view class="intro-copy">
          <text class="intro-title">{{ t('merchantJoin') }}</text>
          <text class="intro-desc">{{ t('merchantApplicationIntro') }}</text>
        </view>
      </view>

      <view v-if="loading" class="state">{{ t('loading') }}</view>
      <view v-else-if="loadError" class="load-error">
        <text>{{ t('supplierLoadFailedDesc') }}</text>
        <text class="retry" @tap="load">{{ t('retry') }}</text>
      </view>
      <view v-else-if="application && application.status !== 'not_registered'" class="card status-card">
        <view class="status-icon" :class="application.status"><AppIcon :name="application.status === 'approved' ? 'verified' : 'order'" :size="42" /></view>
        <text class="status-title">{{ statusTitle }}</text>
        <text class="status-desc">{{ statusDescription }}</text>
        <view v-if="application.status === 'approved'" class="primary-button" @tap="openWorkspace">{{ t('openMerchantWorkspace') }}</view>
      </view>
      <view v-else class="card form-card">
        <view class="field">
          <text class="field-label">{{ t('k_f47e2736') }}</text>
          <input v-model="form.company_name" class="field-input" maxlength="128" :placeholder="t('k_aac0bc4d')" />
        </view>
        <view class="field">
          <text class="field-label">{{ t('k_52409da5') }}</text>
          <input v-model="form.contact" class="field-input" maxlength="64" :placeholder="t('k_60d0458a')" />
        </view>
        <view class="field">
          <text class="field-label">{{ t('k_09a1f698') }}</text>
          <input v-model="form.phone" class="field-input" type="number" maxlength="11" :placeholder="t('k_8098e2b4')" />
        </view>
        <view class="field">
          <text class="field-label">{{ t('region') }}</text>
          <input v-model="form.region" class="field-input" maxlength="64" :placeholder="t('k_5a490d32')" />
        </view>
        <view class="field">
          <text class="field-label">{{ t('k_a784c811') }}</text>
          <textarea v-model="form.desc" class="field-textarea" maxlength="255" :placeholder="t('k_d06427b1')" />
        </view>
        <text class="review-note">{{ t('merchantApplicationReviewNote') }}</text>
        <view class="primary-button" :class="{ disabled: submitting }" @tap="submit">{{ t(submitting ? 'loading' : 'k_4fad0d62') }}</view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getMySupplier, registerSupplier, type SupplierInfo } from '@/api/supplier'
import AppIcon from '@/components/AppIcon.vue'
import AppNavBar from '@/components/AppNavBar.vue'
import { useI18nStore } from '@/store/i18n'
import { useUserStore } from '@/store/user'
import { navigateTo } from '@/utils/nav'

const { t, localizedErrorMessage } = useI18nStore()
const userStore = useUserStore()
const loading = ref(false)
const loadError = ref(false)
const submitting = ref(false)
const application = ref<SupplierInfo | { status: string } | null>(null)
const form = reactive({ company_name: '', contact: '', phone: '', region: '', desc: '' })

const statusTitle = computed(() => {
  if (application.value?.status === 'approved') return t('merchantApplicationApproved')
  if (application.value?.status === 'rejected') return t('merchantApplicationRejected')
  return t('merchantApplicationPending')
})
const statusDescription = computed(() => {
  if (application.value?.status === 'approved') return t('merchantApplicationApprovedHint')
  if (application.value?.status === 'rejected') return t('merchantApplicationRejectedHint')
  return t('merchantApplicationPendingHint')
})

async function load() {
  loading.value = true
  loadError.value = false
  try {
    application.value = await getMySupplier()
    const profile = userStore.userInfo
    if (!form.contact) form.contact = profile?.username || ''
    if (!form.phone) form.phone = profile?.phone || ''
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (submitting.value) return
  const companyName = form.company_name.trim()
  const contact = form.contact.trim()
  const phone = form.phone.trim()
  if (companyName.length < 2 || contact.length < 2) {
    uni.showToast({ title: t('completeMerchantApplication'), icon: 'none' })
    return
  }
  if (!/^1\d{10}$/.test(phone)) {
    uni.showToast({ title: t('enterValidMerchantPhone'), icon: 'none' })
    return
  }
  submitting.value = true
  try {
    application.value = await registerSupplier({
      company_name: companyName,
      contact,
      phone,
      region: form.region.trim() || null,
      desc: form.desc.trim() || null,
    })
    await userStore.fetchProfile().catch(() => undefined)
    uni.showToast({ title: t('入驻申请已提交'), icon: 'success' })
  } catch (error) {
    uni.showToast({ title: localizedErrorMessage(error, 'operationFailed'), icon: 'none' })
  } finally {
    submitting.value = false
  }
}

async function openWorkspace() {
  try {
    if (userStore.role !== 'supplier') await userStore.switchRole()
    navigateTo('/pages/supplier/dashboard')
  } catch {}
}

onShow(load)
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 8rpx 32rpx calc(132rpx + var(--safe-bottom)); }
.intro { display: flex; align-items: center; gap: 20rpx; padding: 26rpx 0 20rpx; }
.intro-icon { width: 82rpx; height: 82rpx; flex-shrink: 0; display: flex; align-items: center; justify-content: center; color: var(--primary); background: var(--primary-soft); border-radius: 22rpx; }
.intro-copy { min-width: 0; }
.intro-title { display: block; color: var(--text); font-size: 34rpx; font-weight: 750; }
.intro-desc { display: block; margin-top: 6rpx; color: var(--text-sub); font-size: 22rpx; line-height: 1.5; }
.card { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }
.state { padding: 80rpx 0; color: var(--text-sub); text-align: center; font-size: 25rpx; }
.load-error { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; padding: 24rpx; color: var(--text-sub); background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); font-size: 23rpx; }
.retry { color: var(--primary); font-weight: 700; }
.form-card { padding: 28rpx 30rpx 32rpx; }
.field { margin-bottom: 26rpx; }
.field-label { display: block; margin-bottom: 10rpx; color: var(--text-sub); font-size: 23rpx; }
.field-input { box-sizing: border-box; width: 100%; min-height: 76rpx; padding: 0 18rpx; color: var(--text); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: 12rpx; font-size: 27rpx; }
.field-textarea { box-sizing: border-box; width: 100%; min-height: 170rpx; padding: 18rpx; color: var(--text); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: 12rpx; font-size: 26rpx; line-height: 1.55; }
.review-note { display: block; margin: 2rpx 0 22rpx; color: var(--text-dim); font-size: 21rpx; line-height: 1.55; }
.primary-button { min-height: 84rpx; display: flex; align-items: center; justify-content: center; color: #fff; background: var(--primary); border-radius: 14rpx; font-size: 28rpx; font-weight: 700; }
.primary-button.disabled { opacity: .5; }
.status-card { padding: 48rpx 34rpx; text-align: center; }
.status-icon { width: 88rpx; height: 88rpx; margin: 0 auto 20rpx; display: flex; align-items: center; justify-content: center; color: var(--primary); background: var(--primary-soft); border-radius: 44rpx; }
.status-icon.approved { color: var(--up); background: var(--up-soft); }
.status-icon.rejected { color: var(--down); background: rgba(217,72,72,.08); }
.status-title { display: block; color: var(--text); font-size: 32rpx; font-weight: 750; }
.status-desc { display: block; margin: 12rpx 0 30rpx; color: var(--text-sub); font-size: 24rpx; line-height: 1.6; }
</style>
