<template>
  <view class="page">
    <AppNavBar :title="t('k_1daa331a')" />
    <view class="shell">
      <view v-if="info?.status === 'approved'" class="card ok-card">
        <text class="ok-icon">✓</text>
        <text class="ok-title">{{ t('k_3ac7ffdd') }}</text>
        <text class="ok-sub">{{ info.company_name }} · {{ info.contact }}</text>
        <view class="btn-primary" @tap="goDashboard">{{ t('k_07c8d3d4') }}</view>
      </view>
      <view v-else-if="info?.status === 'pending'" class="card status-card">
        <text class="status-title">{{ t('商家入驻审核中') }}</text>
        <text class="status-sub">{{ t('审核通过后可切换为商家端并管理设备与订单') }}</text>
      </view>
      <view v-else-if="info?.status === 'rejected'" class="card status-card rejected">
        <text class="status-title">{{ t('商家入驻申请未通过') }}</text>
        <text class="status-sub">{{ t('请联系客服核对资料后重新提交') }}</text>
      </view>
      <template v-else>
        <SectionHeader :title="t('k_54796dca')" />
        <view class="card form">
          <view class="field">
            <text class="flabel">{{ t('k_f47e2736') }}</text>
            <input class="finput" v-model="form.company_name" :placeholder="t('k_aac0bc4d')" placeholder-class="ph" />
          </view>
          <view class="field">
            <text class="flabel">{{ t('k_52409da5') }}</text>
            <input class="finput" v-model="form.contact" :placeholder="t('k_60d0458a')" placeholder-class="ph" />
          </view>
          <view class="field">
            <text class="flabel">{{ t('k_09a1f698') }}</text>
            <input class="finput" v-model="form.phone" type="number" :placeholder="t('k_8098e2b4')" placeholder-class="ph" maxlength="11" />
          </view>
          <view class="field">
            <text class="flabel">{{ t('k_65d3ab77') }}</text>
            <input class="finput" v-model="form.region" :placeholder="t('k_5a490d32')" placeholder-class="ph" />
          </view>
          <view class="field">
            <text class="flabel">{{ t('k_a784c811') }}</text>
            <textarea class="tarea" v-model="form.desc" :placeholder="t('k_d06427b1')" placeholder-class="ph" maxlength="200" />
          </view>
        </view>
        <view class="btn-primary" :class="{ disabled: submitting }" @tap="onSubmit">{{ t(submitting ? '提交中...' : '提交入驻申请') }}</view>
        <view class="tip">{{ t('k_49412090') }}</view>
      </template>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { registerSupplier, getMySupplier, type SupplierInfo } from '@/api/supplier'
import AppNavBar from '@/components/AppNavBar.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import { navigateTo as nav } from '@/utils/nav'
import { useI18nStore } from '@/store/i18n'

const { t } = useI18nStore()
const info = ref<SupplierInfo | null>(null)
const submitting = ref(false)
const form = reactive({ company_name: '', contact: '', phone: '', region: '', desc: '' })

async function load() {
  try {
    const d = await getMySupplier()
    if (d && (d as any).id) info.value = d as SupplierInfo
  } catch {}
}
onShow(() => load())

async function onSubmit() {
  if (!form.company_name || !form.contact || !form.phone) {
    uni.showToast({ title: t('请填写完整'), icon: 'none' }); return
  }
  submitting.value = true
  try {
    await registerSupplier({ ...form })
    uni.showToast({ title: t('入驻申请已提交'), icon: 'success' })
    await load()
  } catch {}
  submitting.value = false
}
function goDashboard() { nav('/pages/supplier/dashboard') }
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--card-border); }
.ok-card { padding: 64rpx 32rpx; text-align: center; margin: 24rpx 0; }
.ok-icon { font-size: 72rpx; color: var(--up); }
.ok-title { display: block; color: var(--text); font-size: 36rpx; font-weight: 700; margin: 16rpx 0 8rpx; }
.ok-sub { display: block; color: var(--text-sub); font-size: 26rpx; margin-bottom: 32rpx; }
.status-card { padding: 64rpx 32rpx; text-align: center; margin: 24rpx 0; background: rgba(24,175,196,0.06); }
.status-card.rejected { background: var(--down-soft); }
.status-title { display: block; color: var(--text); font-size: 34rpx; font-weight: 700; }
.status-sub { display: block; color: var(--text-sub); font-size: 25rpx; line-height: 1.6; margin-top: 16rpx; }
.form { padding: 16rpx 32rpx; margin-bottom: 24rpx; }
.field { margin-bottom: 32rpx; }
.flabel { color: var(--text-sub); font-size: 24rpx; display: block; margin-bottom: 12rpx; }
.finput { color: var(--text); font-size: 32rpx; }
.tarea { width: 100%; min-height: 160rpx; color: var(--text); font-size: 28rpx; line-height: 1.6; }
.ph { color: var(--text-dim); }
.btn-primary { background: linear-gradient(135deg, var(--primary), var(--primary)); color: #fff; text-align: center; padding: 28rpx 0; border-radius: var(--radius); font-size: 30rpx; font-weight: 600; }
.btn-primary.disabled { opacity: 0.4; }
.tip { color: var(--text-dim); font-size: 22rpx; padding: 24rpx 8rpx; line-height: 1.6; }
</style>
