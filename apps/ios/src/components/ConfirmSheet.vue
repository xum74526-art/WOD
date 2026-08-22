<template>
  <view class="mask" v-if="visible" @tap="onMask">
    <view class="sheet" @tap.stop>
      <text class="title">{{ t(title) }}</text>
      <text class="desc" v-if="desc">{{ tr(desc) }}</text>
      <view class="content"><slot /></view>
      <view class="actions">
        <view class="btn cancel" @tap="$emit('cancel')">{{ t(cancelText) }}</view>
        <view class="btn confirm" @tap="$emit('confirm')">{{ t(confirmText) }}</view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { useI18nStore } from '@/store/i18n'

const { t, tr } = useI18nStore()
withDefaults(defineProps<{
  visible: boolean
  title?: string
  desc?: string
  cancelText?: string
  confirmText?: string
}>(), {
  title: '',
  desc: '',
  cancelText: '取消',
  confirmText: '确认',
})

const emit = defineEmits<{ (e: 'cancel'): void; (e: 'confirm'): void }>()
function onMask() { emit('cancel') }
</script>

<style lang="scss" scoped>
.mask { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); z-index: 200; display: flex; align-items: flex-end; }
.sheet { width: 100%; background: var(--card); border-radius: 28rpx 28rpx 0 0; padding: 40rpx 32rpx calc(40rpx + var(--safe-bottom)); }
.title { display: block; color: var(--text); font-size: 32rpx; font-weight: 600; text-align: center; }
.desc { display: block; color: var(--text-sub); font-size: 26rpx; text-align: center; margin-top: 12rpx; }
.content { margin: 32rpx 0; }
.actions { display: flex; gap: 20rpx; }
.btn { flex: 1; text-align: center; padding: 28rpx 0; border-radius: var(--radius); font-size: 30rpx; }
.btn.cancel { background: var(--bg-2); color: var(--text-sub); }
.btn.confirm { background: var(--primary); color: #fff; font-weight: 600; }
</style>
