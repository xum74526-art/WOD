<template>
  <view class="theme-toggle" role="button" :aria-label="label" @tap="toggle">
    <text class="toggle-icon" v-if="isSystem">◐</text>
    <text class="toggle-icon" v-else-if="isDark">☀</text>
    <text class="toggle-icon" v-else>🌙</text>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useThemeStore } from '@/store/theme'
import { useI18nStore } from '@/store/i18n'

const theme = useThemeStore()
const i18n = useI18nStore()
const isDark = computed(() => theme.isDark)
const isSystem = computed(() => theme.mode === 'system')
const label = computed(() => i18n.t(isDark.value ? 'switchToLightTheme' : 'switchToDarkTheme'))

function toggle() {
  theme.toggle()
}
</script>

<style lang="scss" scoped>
.theme-toggle {
  width: 88rpx;
  height: 88rpx;
  border-radius: 44rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--card);
  border: 1rpx solid var(--card-border);
}
.toggle-icon {
  font-size: 32rpx;
  line-height: 1;
}
</style>
