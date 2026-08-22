<template>
  <view class="seg">
    <view
      v-for="(item, i) in items"
      :key="i"
      class="seg-item"
      :class="{ active: modelValue === i }"
      @tap="$emit('update:modelValue', i)"
    >
      <text>{{ t(item) }}</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { useI18nStore } from '@/store/i18n'

const { t } = useI18nStore()
defineProps<{ items: string[]; modelValue: number }>()
defineEmits<{ (e: 'update:modelValue', v: number): void }>()
</script>

<style lang="scss" scoped>
.seg { display: flex; background: var(--card); border-radius: var(--radius); padding: 4rpx; }
.seg-item { flex: 1; text-align: center; padding: 16rpx 0; font-size: 26rpx; color: var(--text-sub); border-radius: var(--radius); transition: all .2s; }
.seg-item.active { background: var(--bg-2); color: var(--text); font-weight: 600; }
</style>
