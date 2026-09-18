<template>
  <view class="page">
    <AppNavBar :title="t('publish')" />
    <view class="shell">
      <view class="card form">
        <textarea class="tarea" v-model="form.content" :placeholder="t('k_a5248a2b')" placeholder-class="ph" maxlength="500" />
        <view class="topic-row">
          <text class="topic-t"># {{ t('话题') }}</text>
          <input class="topic-i" v-model="form.topic" :placeholder="t('k_af4399f5')" placeholder-class="ph" />
        </view>
      </view>
      <view class="btn-primary" :class="{ disabled: submitting }" @tap="onSubmit">
        {{ submitting ? t('提交中...') : t('发布') }}
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { navigateBack } from '@/utils/nav'
import { createPost } from '@/api/community'
import AppNavBar from '@/components/AppNavBar.vue'
import { useI18nStore } from '@/store/i18n'

const { t, localizedErrorMessage } = useI18nStore()
const submitting = ref(false)
const form = reactive({ content: '', topic: '' })

async function onSubmit() {
  if (submitting.value) return
  if (!form.content) {
    uni.showToast({ title: t('请输入内容'), icon: 'none' })
    return
  }
  submitting.value = true
  try {
    await createPost({
      content: form.content,
      topic: form.topic || undefined,
    })
    uni.showToast({ title: t('发布成功'), icon: 'success' })
    setTimeout(() => navigateBack(), 800)
  } catch (error) {
    uni.showToast({ title: localizedErrorMessage(error, '发布失败'), icon: 'none' })
  } finally {
    submitting.value = false
  }
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 24rpx 32rpx calc(132rpx + var(--safe-bottom)); }
.card { padding: 32rpx; border: 1rpx solid var(--card-border); border-radius: var(--radius); background: var(--card); }
.tarea { width: 100%; min-height: 240rpx; color: var(--text); font-size: 28rpx; line-height: 1.6; }
.ph { color: var(--text-dim); }
.topic-row { display: flex; align-items: center; padding-top: 24rpx; border-top: 1rpx solid var(--border); }
.topic-t { color: var(--primary); font-size: 26rpx; font-weight: 600; }
.topic-i { flex: 1; margin-left: 16rpx; color: var(--text); font-size: 26rpx; }
.btn-primary { margin-top: 32rpx; }
.btn-primary.disabled { opacity: 0.5; pointer-events: none; }
</style>
