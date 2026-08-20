<template>
  <view class="page">
    <AppNavBar :title="t('k_7fc88aee')" />
    <view class="shell">
      <view class="card form">
        <view class="field">
          <text class="flabel">{{ t('k_01e94436') }}</text>
          <input class="finput" v-model="form.old_password" :password="!show1" :placeholder="t('k_9c19a424')" placeholder-class="ph" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('k_bf7da0bf') }}</text>
          <input class="finput" v-model="form.new_password" :password="!show2" :placeholder="t('k_002b6972')" placeholder-class="ph" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('k_670d631e') }}</text>
          <input class="finput" v-model="form.confirm" :password="!show2" :placeholder="t('k_ec7b7324')" placeholder-class="ph" />
        </view>
        <view class="btn-primary" :class="{ disabled: submitting }" @tap="onSubmit">{{ t(submitting ? '提交中...' : '确认修改') }}</view>
      </view>
      <view class="risk">{{ t('k_be25d266') }}</view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useUserStore } from '@/store/user'
import * as userApi from '@/api/user'
import AppNavBar from '@/components/AppNavBar.vue'
import { useI18nStore } from '@/store/i18n'

const { t } = useI18nStore()
const userStore = useUserStore()
const form = reactive({ old_password: '', new_password: '', confirm: '' })
const show1 = ref(false)
const show2 = ref(false)
const submitting = ref(false)

async function onSubmit() {
  if (submitting.value) return
  if (!form.old_password || !form.new_password) { uni.showToast({ title: t('pleaseComplete'), icon: 'none' }); return }
  if (form.new_password.length < 6) { uni.showToast({ title: t('新密码至少 6 位'), icon: 'none' }); return }
  if (form.new_password !== form.confirm) { uni.showToast({ title: t('两次密码不一致'), icon: 'none' }); return }
  submitting.value = true
  try {
    await userApi.changePassword(form.old_password, form.new_password)
    uni.showToast({ title: t('修改成功'), icon: 'success' })
    userStore.logout()
    setTimeout(() => uni.reLaunch({ url: '/pages/login/index' }), 800)
  } catch { /* */ }
  submitting.value = false
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--border); }
.form { padding: 16rpx 32rpx; }
.field { margin-bottom: 32rpx; }
.flabel { color: var(--text-sub); font-size: 24rpx; display: block; margin-bottom: 12rpx; }
.finput { color: var(--text); font-size: 32rpx; }
.ph { color: var(--text-dim); }
.btn-primary { background: var(--primary); color: #fff; text-align: center; padding: 28rpx 0; border-radius: var(--radius); font-size: 30rpx; font-weight: 600; }
.btn-primary.disabled { opacity: 0.4; }
.risk { color: var(--text-dim); font-size: 22rpx; padding: 24rpx 8rpx; }
</style>
