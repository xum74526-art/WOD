<template>
  <text class="badge" :class="type">{{ t(text) }}</text>
</template>

<script setup lang="ts">
import { useI18nStore } from '@/store/i18n'

const { t } = useI18nStore()
withDefaults(defineProps<{
  text: string
  type?: 'default' | 'running' | 'done' | 'expired' | 'canceled' | 'up' | 'down'
}>(), {
  type: 'default',
})
</script>

<style lang="scss" scoped>
.badge { display: inline-block; font-size: 22rpx; padding: 6rpx 18rpx; border-radius: var(--radius); }
.default { color: var(--text-sub); background: rgba(15, 35, 45, 0.06); }
.running { color: var(--up); background: var(--up-soft); }
.done { color: var(--text-sub); background: rgba(15, 35, 45, 0.06); }
.expired { color: var(--text-dim); background: rgba(15, 35, 45, 0.04); }
.canceled { color: var(--down); background: var(--down-soft); }
.up { color: var(--up); background: var(--up-soft); }
.down { color: var(--down); background: var(--down-soft); }
</style>
