<template>
  <view
    v-if="open"
    class="asset-panel-picker"
    role="dialog"
    aria-modal="true"
    :aria-label="t('selectComponent')"
    tabindex="0"
  >
    <view class="picker-scrim"></view>

    <view class="picker-sheet">
      <view class="picker-toolbar">
        <view
          class="picker-toolbar-action cancel"
          role="button"
          tabindex="0"
          :aria-label="t('cancel')"
          @tap.stop="cancel"
        >
          {{ t('cancel') }}
        </view>
        <text class="picker-title">{{ t('selectComponent') }}</text>
        <view
          class="picker-toolbar-action done"
          role="button"
          tabindex="0"
          :aria-label="t('done')"
          @tap.stop="confirm"
        >
          {{ t('done') }}
        </view>
      </view>

      <view class="picker-wheel-wrap">
        <view class="picker-fade top"></view>
        <view class="picker-fade bottom"></view>
        <picker-view
          class="picker-wheel"
          :value="[activeIndex]"
          :indicator-style="indicatorStyle"
          :mask-style="maskStyle"
          :immediate-change="true"
          @change="onChange"
        >
          <picker-view-column>
            <view
              v-for="(item, index) in items"
              :key="item.key"
              class="picker-option"
              :class="{
                selected: index === activeIndex,
                nearby: Math.abs(index - activeIndex) === 1,
              }"
              role="option"
              :aria-selected="index === activeIndex"
              @tap.stop="selectIndex(index)"
            >
              <text>{{ item.label }}</text>
            </view>
          </picker-view-column>
        </picker-view>
      </view>

    </view>
  </view>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18nStore } from '@/store/i18n'
import type { AssetPanelKey, AssetPanelOption } from './types'

const props = defineProps<{
  open: boolean
  items: AssetPanelOption[]
  activeKey: AssetPanelKey
}>()

const emit = defineEmits<{
  (event: 'preview', key: AssetPanelKey): void
  (event: 'confirm', key: AssetPanelKey): void
  (event: 'cancel'): void
}>()

const { t } = useI18nStore()
const activeIndex = ref(0)
const reduceMotion = ref(false)
const indicatorStyle = 'height: 96rpx; border-top: 1rpx solid rgba(24,175,196,.28); border-bottom: 1rpx solid rgba(24,175,196,.28);'
const maskStyle = 'background: transparent;'

let previousBodyOverflow = ''
let motionMedia: MediaQueryList | null = null
let motionListener: ((event: MediaQueryListEvent) => void) | null = null

function syncKey(key: AssetPanelKey) {
  const index = props.items.findIndex((item) => item.key === key)
  activeIndex.value = index >= 0 ? index : 0
}

function selectIndex(index: number) {
  const next = Math.max(0, Math.min(index, props.items.length - 1))
  if (next === activeIndex.value) return
  activeIndex.value = next
  emit('preview', props.items[next].key)
  try { uni.vibrateShort({ type: 'light', fail: () => {} }) } catch {}
}

function onChange(event: any) {
  const value = Number(event?.detail?.value?.[0] ?? 0)
  selectIndex(value)
}

function confirm() {
  const item = props.items[activeIndex.value]
  if (item) emit('confirm', item.key)
}

function cancel() {
  emit('cancel')
}

function lockPage(locked: boolean) {
  // #ifdef H5
  if (typeof document !== 'undefined') {
    if (locked) {
      previousBodyOverflow = document.body.style.overflow
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = previousBodyOverflow
    }
  }
  // #endif
}

function setTabBarHidden(hidden: boolean) {
  try {
    if (hidden) uni.hideTabBar({ animation: !reduceMotion.value, fail: () => {} })
    else uni.showTabBar({ animation: !reduceMotion.value, fail: () => {} })
  } catch {}
}

function onKeydown(event: KeyboardEvent) {
  if (!props.open) return
  if (event.key === 'ArrowUp') {
    event.preventDefault()
    selectIndex(activeIndex.value - 1)
  } else if (event.key === 'ArrowDown') {
    event.preventDefault()
    selectIndex(activeIndex.value + 1)
  } else if (event.key === 'Enter') {
    event.preventDefault()
    confirm()
  } else if (event.key === 'Escape') {
    event.preventDefault()
    cancel()
  }
}

watch(() => props.activeKey, (key) => syncKey(key))

watch(() => props.open, async (open) => {
  if (open) {
    syncKey(props.activeKey)
    lockPage(true)
    setTabBarHidden(true)
    await nextTick()
    // #ifdef H5
    document.querySelector<HTMLElement>('.asset-panel-picker')?.focus()
    // #endif
  } else {
    lockPage(false)
    setTabBarHidden(false)
  }
}, { immediate: true })

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
  lockPage(false)
  if (props.open) setTabBarHidden(false)
  // #ifdef H5
  window.removeEventListener('keydown', onKeydown)
  if (motionListener) motionMedia?.removeEventListener?.('change', motionListener)
  // #endif
})
</script>

<style lang="scss" scoped>
.asset-panel-picker {
  position: fixed;
  inset: 0;
  z-index: 10000;
  min-height: 100vh;
  min-height: 100dvh;
  overflow: hidden;
  outline: none;
  animation: picker-in 180ms ease both;
}
.picker-scrim {
  position: absolute;
  inset: 0;
  background: rgba(5, 15, 20, 0.58);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}
.picker-sheet {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  min-height: 650rpx;
  padding-bottom: calc(24rpx + var(--safe-bottom));
  border-radius: 28rpx 28rpx 0 0;
  background: var(--bg);
  box-shadow: 0 -20rpx 70rpx rgba(0, 20, 28, 0.2);
  animation: sheet-up 260ms cubic-bezier(0.2, 0.75, 0.25, 1) both;
}
.picker-toolbar {
  height: 104rpx;
  display: grid;
  grid-template-columns: 150rpx minmax(0, 1fr) 150rpx;
  align-items: center;
  border-bottom: 1rpx solid var(--divider);
  padding: 0 24rpx;
}
.picker-toolbar-action {
  min-height: 76rpx;
  display: flex;
  align-items: center;
  font-size: 28rpx;
  font-weight: 600;
}
.picker-toolbar-action.cancel { justify-content: flex-start; color: var(--text-sub); }
.picker-toolbar-action.done { justify-content: flex-end; color: var(--primary); }
.picker-toolbar-action:active { transform: scale(0.97); }
.picker-title {
  color: var(--text);
  font-size: 28rpx;
  font-weight: 720;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.picker-wheel-wrap { position: relative; height: 480rpx; overflow: hidden; }
.picker-wheel { position: relative; z-index: 2; width: 100%; height: 480rpx; }
.picker-option {
  height: 96rpx;
  padding: 0 38rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-dim);
  font-size: 28rpx;
  text-align: center;
  transition: color 160ms ease, font-size 160ms ease, opacity 160ms ease;
}
.picker-option.nearby { color: var(--text-sub); font-size: 30rpx; }
.picker-option.selected { color: var(--text); font-size: 34rpx; font-weight: 720; }
.picker-fade { position: absolute; left: 0; right: 0; z-index: 4; height: 78rpx; pointer-events: none; }
.picker-fade.top { top: 0; background: linear-gradient(180deg, var(--bg), transparent); }
.picker-fade.bottom { bottom: 0; background: linear-gradient(0deg, var(--bg), transparent); }
@keyframes picker-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes sheet-up { from { transform: translateY(70rpx); opacity: 0.75; } to { transform: translateY(0); opacity: 1; } }

@media (prefers-reduced-motion: reduce) {
  .asset-panel-picker, .picker-sheet { animation-duration: 80ms; }
  .picker-option { transition: none; }
}

@media (prefers-reduced-transparency: reduce) {
  .picker-scrim { background: rgba(5, 15, 20, 0.78); backdrop-filter: none; -webkit-backdrop-filter: none; }
}
</style>
