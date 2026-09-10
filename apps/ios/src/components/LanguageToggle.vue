<template>
  <view class="language-control">
    <view
      class="lang-toggle"
      :class="{ open: selectorVisible }"
      role="button"
      tabindex="0"
      aria-haspopup="dialog"
      :aria-expanded="selectorVisible ? 'true' : 'false'"
      :aria-label="`${i18n.t('switchLanguage')}: ${currentOption.label}`"
      @tap="selectorVisible = true"
      @keydown.enter="selectorVisible = true"
      @keydown.space.prevent="selectorVisible = true"
    >
      <AppIcon class="lang-icon" name="language" :size="28" aria-hidden="true" />
      <text class="lang-text">{{ currentOption.shortLabel }}</text>
      <AppIcon class="lang-chevron" name="chevron-down" :size="18" aria-hidden="true" />
    </view>

    <LanguageSelectorSheet v-model:visible="selectorVisible" />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import LanguageSelectorSheet from '@/components/LanguageSelectorSheet.vue'
import { useI18nStore } from '@/store/i18n'
import { languageOption } from '@/utils/language'

const i18n = useI18nStore()
const selectorVisible = ref(false)
const currentOption = computed(() => languageOption(i18n.lang))
</script>

<style lang="scss" scoped>
.language-control { display: inline-flex; }

.lang-toggle {
  min-width: 132rpx;
  height: 76rpx;
  box-sizing: border-box;
  padding: 0 19rpx;
  border: 1rpx solid var(--card-border);
  border-radius: 999rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9rpx;
  color: var(--text-sub);
  background: var(--card);
  box-shadow: 0 8rpx 24rpx rgba(9, 69, 78, 0.07);
  transition: transform 150ms ease, border-color 180ms ease, color 180ms ease, background 180ms ease, box-shadow 180ms ease;
}

.lang-toggle.open {
  border-color: rgba(24, 175, 196, 0.36);
  color: var(--primary);
  background: var(--primary-soft);
  box-shadow: 0 8rpx 24rpx rgba(9, 69, 78, 0.1);
}

.lang-toggle:active { transform: scale(0.98); }
.lang-icon, .lang-chevron { flex: 0 0 auto; }
.lang-icon { color: var(--primary); }
.lang-text {
  color: var(--text);
  font-size: 23rpx;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
  letter-spacing: -0.3rpx;
}
.lang-toggle.open .lang-text { color: var(--primary); }
.lang-chevron { transition: transform 180ms ease; }
.lang-toggle.open .lang-chevron { transform: rotate(180deg); }

@media (prefers-reduced-motion: reduce) {
  .lang-toggle, .lang-chevron { transition: none; }
}
</style>
