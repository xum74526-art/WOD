<template>
  <view class="sh">
    <text class="sh-title">{{ t(title) }}</text>
    <view class="sh-extra" v-if="$slots.extra"><slot name="extra" /></view>
  </view>
</template>

<script setup lang="ts">
import { useI18nStore } from '@/store/i18n'

const { t } = useI18nStore()
defineProps<{ title: string }>()
</script>

<style lang="scss" scoped>
.sh { display: flex; justify-content: space-between; align-items: center; margin: 32rpx 0 16rpx; }
.sh-title { color: var(--text); font-size: 15px; font-weight: 700; }
.sh-extra { color: var(--text-sub); font-size: 12px; display: flex; align-items: center; gap: 6rpx; }
</style>
