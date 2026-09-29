<template>
  <view
    v-if="visible"
    class="language-layer"
    role="dialog"
    aria-modal="true"
    :aria-label="t('switchLanguage')"
    tabindex="0"
    @tap="close"
    @touchmove.stop.prevent
  >
    <view class="language-sheet" @tap.stop>
      <view class="sheet-handle" aria-hidden="true" />

      <view class="sheet-header">
        <view class="sheet-heading">
          <view class="heading-icon" aria-hidden="true">
            <AppIcon name="language" :size="34" />
          </view>
          <view class="heading-copy">
            <text class="sheet-title">{{ t('switchLanguage') }}</text>
            <text class="sheet-current">{{ currentOption.label }} · {{ currentOption.locale }} · {{ currentCurrency }}</text>
          </view>
        </view>
        <view
          class="sheet-close"
          role="button"
          tabindex="0"
          :aria-label="t('cancel')"
          @tap="close"
          @keydown.enter="close"
          @keydown.space.prevent="close"
        >
          <text>{{ t('done') }}</text>
        </view>
      </view>

      <view class="language-options" role="radiogroup" :aria-label="t('language')">
        <view
          v-for="option in LANGUAGE_OPTIONS"
          :key="option.language"
          class="language-option"
          :class="{ selected: option.language === i18n.lang }"
          role="radio"
          tabindex="0"
          :aria-checked="option.language === i18n.lang ? 'true' : 'false'"
          :aria-label="`${option.label}, ${option.locale}`"
          @tap="selectLanguage(option.language)"
          @keydown.enter="selectLanguage(option.language)"
          @keydown.space.prevent="selectLanguage(option.language)"
        >
          <view class="language-mark" aria-hidden="true">
            <text>{{ option.mark }}</text>
          </view>
          <view class="language-copy">
            <text class="language-name">{{ option.label }}</text>
            <text class="language-code">{{ option.locale }}</text>
          </view>
          <view class="language-check" :class="{ active: option.language === i18n.lang }" aria-hidden="true">
            <AppIcon v-if="option.language === i18n.lang" name="check" :size="27" />
          </view>
        </view>
      </view>

      <view class="currency-section">
        <view class="currency-heading">
          <text class="currency-title">{{ t('displayCurrency') }}</text>
          <text class="currency-subtitle">{{ t('displayCurrencyReferenceOnly') }}</text>
        </view>
        <view class="currency-options" role="radiogroup" :aria-label="t('displayCurrency')">
          <view
            v-for="option in CURRENCY_OPTIONS"
            :key="option.value"
            class="currency-option"
            :class="{ selected: option.value === currentCurrency }"
            role="radio"
            tabindex="0"
            :aria-checked="option.value === currentCurrency ? 'true' : 'false'"
            @tap="selectCurrency(option.value)"
            @keydown.enter="selectCurrency(option.value)"
            @keydown.space.prevent="selectCurrency(option.value)"
          >
            <text class="currency-symbol">{{ option.symbol }}</text>
            <text class="currency-name">{{ t(option.label) }}</text>
            <text class="currency-code">{{ option.value }}</text>
            <AppIcon v-if="option.value === currentCurrency" name="check" :size="24" />
          </view>
        </view>
        <text class="currency-note">{{ t('cnySettlementAlways') }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import { useI18nStore } from '@/store/i18n'
import { displayCurrencyCode, setDisplayCurrency, type DisplayCurrencyCode } from '@/utils/format'
import {
  LANGUAGE_OPTIONS,
  languageOption,
  type AppLanguage,
} from '@/utils/language'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ (event: 'update:visible', value: boolean): void }>()
const i18n = useI18nStore()
const { t } = i18n
const currentOption = computed(() => languageOption(i18n.lang))
const currentCurrency = computed(() => displayCurrencyCode())
const CURRENCY_OPTIONS: Array<{ value: DisplayCurrencyCode; label: string; symbol: string }> = [
  { value: 'CNY', label: 'currencyCny', symbol: '¥' },
  { value: 'HKD', label: 'currencyHkd', symbol: 'HK$' },
  { value: 'USD', label: 'currencyUsd', symbol: 'US$' },
]
const reduceMotion = ref(false)

let previousBodyOverflow = ''
let previousFocus: HTMLElement | null = null
let tabBarHideRequested = false
let disposed = false
let motionMedia: MediaQueryList | null = null
let motionListener: ((event: MediaQueryListEvent) => void) | null = null

function hideNativeTabBar() {
  // #ifdef APP-PLUS
  if (tabBarHideRequested) return
  tabBarHideRequested = true
  try {
    uni.hideTabBar({
      animation: !reduceMotion.value,
      success: () => {
        if (!props.visible || disposed || !tabBarHideRequested) showNativeTabBar(true)
      },
      fail: () => { tabBarHideRequested = false },
    })
  } catch {
    tabBarHideRequested = false
  }
  // #endif
}

function showNativeTabBar(force = false) {
  // #ifdef APP-PLUS
  if (!tabBarHideRequested && !force) return
  tabBarHideRequested = false
  try {
    uni.showTabBar({ animation: !reduceMotion.value, fail: () => {} })
  } catch {}
  // #endif
}

function close() {
  emit('update:visible', false)
}

function selectLanguage(language: AppLanguage) {
  if (language !== i18n.lang) i18n.setLanguage(language)
}

function selectCurrency(currency: DisplayCurrencyCode) {
  setDisplayCurrency(currency)
}

function lockPage(locked: boolean) {
  // #ifdef H5
  if (typeof document === 'undefined') return
  if (locked) {
    previousBodyOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = previousBodyOverflow
  }
  // #endif
}

function restoreFocus() {
  // #ifdef H5
  const target = previousFocus
  previousFocus = null
  void nextTick(() => target?.focus())
  // #endif
}

function onKeydown(event: KeyboardEvent) {
  if (props.visible && event.key === 'Escape') {
    event.preventDefault()
    close()
  }
}

watch(
  () => props.visible,
  async (visible) => {
    if (visible) {
      // #ifdef H5
      previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
      // #endif
      lockPage(true)
      hideNativeTabBar()
      await nextTick()
      // #ifdef H5
      document.querySelector<HTMLElement>('.language-layer')?.focus()
      // #endif
    } else {
      lockPage(false)
      showNativeTabBar()
      restoreFocus()
    }
  },
  { immediate: true },
)

onMounted(() => {
  // #ifdef H5
  window.addEventListener('keydown', onKeydown)
  motionMedia = window.matchMedia('(prefers-reduced-motion: reduce)')
  reduceMotion.value = motionMedia.matches
  motionListener = (event: MediaQueryListEvent) => { reduceMotion.value = event.matches }
  motionMedia.addEventListener?.('change', motionListener)
  // #endif
})

onBeforeUnmount(() => {
  disposed = true
  lockPage(false)
  showNativeTabBar()
  restoreFocus()
  // #ifdef H5
  window.removeEventListener('keydown', onKeydown)
  if (motionListener) motionMedia?.removeEventListener?.('change', motionListener)
  // #endif
})
</script>

<style lang="scss" scoped>
.language-layer {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  box-sizing: border-box;
  min-height: 100vh;
  min-height: 100dvh;
  padding: 0 24rpx calc(18rpx + var(--safe-bottom));
  overflow: hidden;
  outline: none;
  background: rgba(5, 18, 22, 0.46);
  -webkit-backdrop-filter: blur(8rpx) saturate(112%);
  backdrop-filter: blur(8rpx) saturate(112%);
  animation: language-fade-in 180ms ease-out both;
}

.language-sheet {
  position: relative;
  width: 100%;
  max-width: 700rpx;
  box-sizing: border-box;
  overflow: hidden;
  padding: 18rpx 28rpx 30rpx;
  border: 1rpx solid var(--border);
  border-radius: 38rpx;
  background: var(--overlay-card-bg);
  box-shadow: 0 28rpx 90rpx rgba(5, 35, 40, 0.24), inset 0 1rpx 0 rgba(255, 255, 255, 0.48);
  animation: language-sheet-in 260ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

.sheet-handle {
  width: 66rpx;
  height: 7rpx;
  margin: 0 auto 24rpx;
  border-radius: 999rpx;
  background: var(--text-dim);
  opacity: 0.72;
}

.sheet-header,
.sheet-heading,
.language-option { display: flex; align-items: center; }
.sheet-header { justify-content: space-between; gap: 20rpx; margin-bottom: 28rpx; }
.sheet-heading { min-width: 0; gap: 18rpx; }

.heading-icon {
  width: 72rpx;
  height: 72rpx;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1rpx solid rgba(24, 175, 196, 0.16);
  border-radius: 22rpx;
  color: var(--primary);
  background: var(--primary-soft);
}

.heading-copy,
.language-copy { min-width: 0; display: flex; flex-direction: column; }
.sheet-title { color: var(--text); font-size: 34rpx; font-weight: 760; line-height: 1.25; letter-spacing: -0.4rpx; }
.sheet-current { margin-top: 5rpx; color: var(--text-sub); font-size: 21rpx; line-height: 1.3; }

.sheet-close {
  min-width: 84rpx;
  min-height: 68rpx;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  padding: 0 18rpx;
  border: 1rpx solid var(--border);
  border-radius: 999rpx;
  color: var(--text-sub);
  background: var(--bg-2);
  font-size: 24rpx;
  transition: transform 150ms ease, border-color 150ms ease, color 150ms ease;
}

.language-options { display: flex; flex-direction: column; gap: 14rpx; }
.language-option {
  min-height: 108rpx;
  box-sizing: border-box;
  padding: 16rpx 18rpx;
  border: 1rpx solid transparent;
  border-radius: 25rpx;
  color: var(--text);
  background: var(--bg-2);
  transition: transform 150ms ease, border-color 180ms ease, background 180ms ease;
}
.language-option.selected { border-color: var(--primary); background: var(--primary-soft); }

.language-mark {
  width: 70rpx;
  height: 70rpx;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1rpx solid var(--border);
  border-radius: 21rpx;
  color: var(--text-sub);
  background: var(--card);
  font-size: 24rpx;
  font-weight: 760;
  letter-spacing: -0.3rpx;
}
.selected .language-mark { border-color: transparent; color: var(--primary); background: var(--overlay-card-bg); }
.language-copy { flex: 1; margin-left: 20rpx; }
.language-name { color: var(--text); font-size: 29rpx; font-weight: 650; line-height: 1.25; }
.language-code { margin-top: 5rpx; color: var(--text-sub); font-size: 20rpx; line-height: 1.2; font-variant-numeric: tabular-nums; letter-spacing: 0.5rpx; }

.language-check {
  width: 46rpx;
  height: 46rpx;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1rpx solid var(--border);
  border-radius: 50%;
  color: transparent;
  background: transparent;
}
.language-check.active {
  border-color: var(--primary);
  color: #fff;
  background: var(--primary);
  box-shadow: 0 8rpx 20rpx rgba(24, 175, 196, 0.22);
}

.currency-section { margin-top: 26rpx; padding-top: 24rpx; border-top: 1rpx solid var(--divider); }
.currency-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 18rpx; margin-bottom: 14rpx; }
.currency-title { color: var(--text); font-size: 28rpx; font-weight: 730; }
.currency-subtitle { color: var(--text-sub); font-size: 20rpx; }
.currency-options { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12rpx; }
.currency-option { position: relative; min-height: 112rpx; padding: 14rpx 10rpx; display: flex; flex-direction: column; align-items: center; justify-content: center; border: 1rpx solid var(--border); border-radius: 20rpx; color: var(--text-sub); background: var(--bg-2); }
.currency-option.selected { border-color: var(--primary); color: var(--primary); background: var(--primary-soft); }
.currency-option :deep(.app-icon) { position: absolute; top: 8rpx; right: 8rpx; }
.currency-symbol { color: currentColor; font-size: 27rpx; font-weight: 800; }
.currency-name { margin-top: 5rpx; color: var(--text); font-size: 21rpx; font-weight: 650; }
.currency-code { margin-top: 2rpx; font-size: 17rpx; font-variant-numeric: tabular-nums; }
.currency-note { display: block; margin-top: 14rpx; color: var(--text-sub); font-size: 19rpx; line-height: 1.5; }

.sheet-close:active,
.language-option:active,
.currency-option:active { transform: scale(0.985); }
.sheet-close:focus-visible,
.language-option:focus-visible,
.currency-option:focus-visible { outline: 3rpx solid var(--primary); outline-offset: 2rpx; }

@keyframes language-fade-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes language-sheet-in {
  from { opacity: 0; transform: translateY(30rpx) scale(0.985); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

@media (prefers-reduced-motion: reduce) {
  .language-layer, .language-sheet { animation: none; }
  .sheet-close, .language-option { transition: none; }
}

@media (prefers-reduced-transparency: reduce) {
  .language-layer {
    background: rgba(5, 18, 22, 0.74);
    -webkit-backdrop-filter: none;
    backdrop-filter: none;
  }
}
</style>
