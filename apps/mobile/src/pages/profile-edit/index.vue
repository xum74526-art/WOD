<template>
  <view class="page">
    <AppNavBar :title="t('k_749ba571')" />
    <view class="shell">
      <view class="card avatar-row">
        <view class="avatar" @tap="changeAvatar">
          <image v-if="avatarUrl" class="avatar-img" :src="avatarUrl" mode="aspectFill" @error="avatarLoadFailed = true" />
          <text v-else>{{ avatarText }}</text>
        </view>
        <text class="avatar-tip">{{ t('k_5f944660') }}</text>
      </view>
      <view class="card form">
        <view class="field">
          <text class="flabel">{{ t('k_23eb0e60') }}</text>
          <input class="finput" v-model="form.username" :placeholder="t('k_916ff9ed')" placeholder-class="ph" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('k_8098e2b4') }}</text>
          <view class="readonly-value">{{ phoneDisplay }}</view>
          <text class="field-hint">{{ phoneHint }}</text>
        </view>
        <view class="btn-primary" :class="{ disabled: submitting }" @tap="onSave">{{ t(submitting ? '保存中...' : '保存') }}</view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { reactive, ref, computed } from 'vue'
import { navigateBack } from '@/utils/nav'
import { onShow } from '@dcloudio/uni-app'
import { useUserStore } from '@/store/user'
import * as userApi from '@/api/user'
import AppNavBar from '@/components/AppNavBar.vue'
import { useI18nStore } from '@/store/i18n'
import { localizePersonName } from '@/utils/localize-content'
import { resolveApiMediaUrl } from '@/utils/config'

const i18n = useI18nStore()
const { t } = i18n
const userStore = useUserStore()
const user = computed(() => userStore.userInfo)
const form = reactive({ username: '' })
const pendingAvatarPath = ref('')
const avatarLoadFailed = ref(false)
const avatarText = computed(() => localizePersonName(form.username || user.value?.username || 'K', i18n.lang).slice(0, 1).toUpperCase())
const avatarUrl = computed(() => avatarLoadFailed.value ? '' : (pendingAvatarPath.value || resolveApiMediaUrl(user.value?.avatar)))
const phoneDisplay = computed(() => user.value?.phone || t('phoneNotBound'))
const phoneHint = computed(() => {
  if (!user.value?.phone) return t('phoneBindingFutureHint')
  return user.value.phone_bound === false ? t('closedTestPhoneNotice') : t('phoneReadOnlyHint')
})
const submitting = ref(false)

onShow(async () => {
  if (!userStore.userInfo) {
    try { await userStore.fetchProfile() } catch {}
  }
  form.username = userStore.userInfo?.username || ''
  pendingAvatarPath.value = ''
  avatarLoadFailed.value = false
})

function changeAvatar() {
  uni.chooseImage({
    count: 1,
    sizeType: ['compressed'],
    success: (res) => {
      const selectedFiles = Array.isArray(res.tempFiles) ? res.tempFiles : [res.tempFiles]
      const selected = selectedFiles[0] as { size?: number } | undefined
      if ((selected?.size || 0) > 2 * 1024 * 1024) {
        uni.showToast({ title: t('avatarTooLarge'), icon: 'none' })
        return
      }
      pendingAvatarPath.value = res.tempFilePaths[0]
      avatarLoadFailed.value = false
    },
  })
}

async function onSave() {
  if (submitting.value) return
  if (!form.username) { uni.showToast({ title: t('k_916ff9ed'), icon: 'none' }); return }
  submitting.value = true
  try {
    if (pendingAvatarPath.value) {
      await userApi.uploadAvatar(pendingAvatarPath.value)
      pendingAvatarPath.value = ''
    }
    await userApi.updateProfile({ username: form.username })
    await userStore.fetchProfile()
    uni.showToast({ title: t('保存成功'), icon: 'success' })
    setTimeout(() => navigateBack(), 600)
  } catch { /* request layer already reports the error */ }
  finally { submitting.value = false }
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--border); }
.avatar-row { display: flex; flex-direction: column; align-items: center; padding: 48rpx; margin-bottom: 24rpx; }
.avatar { width: 120rpx; height: 120rpx; border-radius: 60rpx; background: linear-gradient(135deg, var(--primary), var(--primary)); color: #fff; font-size: 52rpx; font-weight: 700; display: flex; align-items: center; justify-content: center; overflow: hidden; }
.avatar-img { width: 120rpx; height: 120rpx; }
.avatar-tip { color: var(--text-sub); font-size: 24rpx; margin-top: 16rpx; }
.form { padding: 16rpx 32rpx; }
.field { margin-bottom: 32rpx; }
.flabel { color: var(--text-sub); font-size: 24rpx; display: block; margin-bottom: 12rpx; }
.finput { color: var(--text); font-size: 32rpx; }
.readonly-value { color: var(--text); font-size: 32rpx; line-height: 48rpx; padding: 4rpx 0; }
.field-hint { display: block; color: var(--text-dim); font-size: 22rpx; line-height: 34rpx; margin-top: 8rpx; }
.ph { color: var(--text-dim); }
.btn-primary { background: var(--primary); color: #fff; text-align: center; padding: 28rpx 0; border-radius: var(--radius); font-size: 30rpx; font-weight: 600; }
.btn-primary.disabled { opacity: 0.4; }
</style>
