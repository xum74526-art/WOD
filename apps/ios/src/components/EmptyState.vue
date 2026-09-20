<template>
  <view class="empty">
    <view class="icon"><slot /></view>
    <text class="text">{{ t(text || '') }}</text>
  </view>
</template>

<script setup lang="ts">
import { useI18nStore } from '@/store/i18n'

const { t } = useI18nStore()
defineProps<{ text?: string }>()
</script>

<style lang="scss" scoped>
.empty { padding: 120rpx 0; text-align: center; }
.icon { margin-bottom: 24rpx; color: var(--text-dim); }
.text { color: var(--text-sub); font-size: 26rpx; }
</style>
