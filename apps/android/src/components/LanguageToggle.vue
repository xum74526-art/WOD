<template>
  <view class="lang-toggle" role="button" aria-haspopup="menu" :aria-label="i18n.t('switchLanguage')" @tap="openLanguageSelector">
    <text class="lang-text">{{ languageMark }}</text>
    <text class="lang-chevron" aria-hidden="true">▾</text>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18nStore } from '@/store/i18n'
import type { AppLanguage } from '@/utils/language'

const i18n = useI18nStore()
const languageOptions: Array<{ language: AppLanguage; label: string }> = [
  { language: 'zh-Hant', label: '繁體中文' },
  { language: 'zh-Hans', label: '简体中文' },
  { language: 'en', label: 'English' },
]
const languageMark = computed(() => ({
  'zh-Hant': '繁',
  'zh-Hans': '简',
  en: 'EN',
}[i18n.lang]))

function openLanguageSelector() {
  uni.showActionSheet({
    title: i18n.t('switchLanguage'),
    itemList: languageOptions.map((option) => option.language === i18n.lang ? `✓ ${option.label}` : option.label),
    success: ({ tapIndex }) => {
      const selected = languageOptions[tapIndex]
      if (selected && selected.language !== i18n.lang) i18n.setLanguage(selected.language)
    },
  })
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
  gap: 4rpx;
  background: var(--card);
  border: 1rpx solid var(--card-border);
}
.lang-text {
  font-size: 22rpx;
  font-weight: 700;
  color: var(--text);
}
.lang-chevron {
  margin-top: 2rpx;
  font-size: 16rpx;
  color: var(--text-sub);
}
</style>
