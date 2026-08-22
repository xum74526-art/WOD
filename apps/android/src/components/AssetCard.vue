<template>
  <view class="card">
    <view class="card-row">
      <text class="label">{{ t(label) }}</text>
      <text class="value" :class="valueClass">{{ value }}</text>
    </view>
    <slot />
  </view>
</template>

<script setup lang="ts">
import { useI18nStore } from '@/store/i18n'

const { t } = useI18nStore()
defineProps<{ label: string; value: string; valueClass?: string }>()
</script>

<style lang="scss" scoped>
.card {
  background: var(--card);
  border-radius: 24rpx;
  padding: 32rpx;
  border: 1rpx solid var(--border);
}
.card-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.label {
  color: var(--text-sub);
  font-size: 26rpx;
}
.value {
  color: var(--text);
  font-size: 40rpx;
  font-weight: 600;
}
.value-up { color: var(--up); }
.value-down { color: var(--down); }
</style>
