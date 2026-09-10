<template>
  <view class="lang-toggle" role="button" :aria-label="i18n.t('switchLanguage')" @tap="toggle">
    <text class="lang-text">{{ languageMark }}</text>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18nStore } from '@/store/i18n'

const i18n = useI18nStore()
const languageMark = computed(() => ({
  'zh-Hant': '繁',
  'zh-Hans': '简',
  en: 'EN',
}[i18n.lang]))

function toggle() {
  i18n.toggle()
}
</script>

<style lang="scss" scoped>
.lang-toggle {
  width: 88rpx;
  height: 88rpx;
  border-radius: 44rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--card);
  border: 1rpx solid var(--card-border);
}
.lang-text {
  font-size: 22rpx;
  font-weight: 700;
  color: var(--text);
}
</style>
