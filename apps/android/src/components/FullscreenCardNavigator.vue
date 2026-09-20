<template>
  <view
    v-if="open"
    class="fullscreen-card-navigator"
    role="dialog"
    aria-modal="true"
    :aria-label="title"
    tabindex="0"
    @touchstart="onTouchStart"
    @touchmove.stop.prevent="onTouchMove"
    @touchend="onTouchEnd"
    @touchcancel="onTouchEnd"
  >
    <view class="overlay-surface"></view>

    <view class="navigator-header">
      <view class="header-copy">
        <text class="navigator-title">{{ title }}</text>
        <text class="navigator-subtitle">{{ t('selectedCard', { name: activeCard?.title || '' }) }}</text>
      </view>
      <view
        class="close-button"
        role="button"
        tabindex="0"
        :aria-label="t('close')"
        @tap.stop="close"
      >
        <text>{{ t('close') }}</text>
      </view>
    </view>

    <view class="card-stage">
      <view
        v-for="(card, index) in cards"
        :key="card.key"
        class="navigator-card"
        :class="{
          active: index === activeIndex,
          adjacent: Math.abs(index - activeIndex) === 1,
          dragging,
        }"
        :style="cardStyle(index)"
        role="button"
        :tabindex="index === activeIndex ? 0 : -1"
        :aria-label="card.title"
        @tap.stop="onCardTap(index)"
      >
        <view class="card-accent"></view>
        <view class="card-head">
          <view class="card-icon"><AppIcon :name="card.icon" :size="38" /></view>
          <view class="card-heading">
            <text class="card-title">{{ card.title }}</text>
            <text class="card-description">{{ card.description }}</text>
          </view>
        </view>

        <view v-if="card.state === 'loading'" class="skeleton-metrics" aria-hidden="true">
          <view v-for="n in 3" :key="n" class="skeleton-metric">
            <view class="skeleton-line value"></view>
            <view class="skeleton-line label"></view>
          </view>
        </view>

        <view v-else-if="card.state === 'error'" class="card-state">
          <text class="state-title">{{ card.stateText || t('dataUnavailable') }}</text>
          <view class="state-action" @tap.stop="$emit('retry', card.key)">{{ t('retry') }}</view>
        </view>

        <view v-else class="metric-grid">
          <view v-for="metric in card.metrics" :key="metric.label" class="metric-item">
            <text class="metric-value" :class="metric.tone || ''">{{ metric.value }}</text>
            <text class="metric-label">{{ metric.label }}</text>
          </view>
        </view>

        <view v-if="card.state !== 'loading' && card.state !== 'error'" class="card-footer">
          <text v-if="card.footnote" class="card-footnote">{{ card.footnote }}</text>
          <view class="card-action" @tap.stop="confirmActive">
            <text>{{ card.actionLabel }}</text>
            <AppIcon name="arrow-right" :size="28" />
          </view>
        </view>
      </view>
    </view>

    <view class="navigator-footer">
      <text class="position-label">{{ activeIndex + 1 }} / {{ cards.length }}</text>
      <text class="gesture-hint">{{ t('swipeToSelect') }}</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, type CSSProperties } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import { useI18nStore } from '@/store/i18n'

interface NavigatorMetric {
  label: string
  value: string
  tone?: 'positive' | 'warning' | 'danger' | ''
}

interface NavigatorCard {
  key: string
  title: string
  description: string
  icon: string
  metrics: NavigatorMetric[]
  actionLabel: string
  footnote?: string
  state?: 'ready' | 'loading' | 'empty' | 'error'
  stateText?: string
}

const props = withDefaults(defineProps<{
  open: boolean
  title: string
  cards: NavigatorCard[]
  activeKey?: string
}>(), {
  activeKey: '',
})

const emit = defineEmits<{
  (event: 'select', key: string): void
  (event: 'confirm', key: string): void
  (event: 'close'): void
  (event: 'retry', key: string): void
}>()

const { t } = useI18nStore()
const activeIndex = ref(0)
const dragging = ref(false)
const dragOffset = ref(0)
const viewportHeight = ref(720)
const reduceMotion = ref(false)

let touchStartY = 0
let touchStartAt = 0
let suppressTapUntil = 0
let previousBodyOverflow = ''
let motionMedia: MediaQueryList | null = null

const activeCard = computed(() => props.cards[activeIndex.value])

function syncActiveKey(key: string) {
  const index = props.cards.findIndex((card) => card.key === key)
  activeIndex.value = index >= 0 ? index : 0
  dragOffset.value = 0
}

function updateViewport() {
  try {
    viewportHeight.value = uni.getSystemInfoSync().windowHeight || 720
  } catch {
    viewportHeight.value = 720
  }
}

function cardStyle(index: number): CSSProperties {
  const step = Math.min(viewportHeight.value * 0.53, 460)
  const relative = index - activeIndex.value
  const offset = relative * step + dragOffset.value
  const virtualDistance = Math.min(Math.abs(relative + dragOffset.value / step), 2)
  const scale = Math.max(0.88, 1 - virtualDistance * 0.065)
  const opacity = virtualDistance > 1.4 ? 0 : Math.max(0.38, 1 - virtualDistance * 0.52)
  return {
    transform: `translate3d(-50%, calc(-50% + ${offset}px), 0) scale(${scale})`,
    opacity: String(opacity),
    zIndex: String(20 - Math.round(virtualDistance * 4)),
    pointerEvents: Math.abs(relative) <= 1 ? 'auto' : 'none',
    transitionDuration: reduceMotion.value ? '80ms' : undefined,
  }
}

function selectIndex(index: number) {
  const next = Math.max(0, Math.min(index, props.cards.length - 1))
  if (next === activeIndex.value) return
  activeIndex.value = next
  dragOffset.value = 0
  emit('select', props.cards[next].key)
  try { uni.vibrateShort({ type: 'light', fail: () => {} }) } catch {}
}

function onTouchStart(event: any) {
  const touch = event.touches?.[0]
  if (!touch) return
  dragging.value = true
  touchStartY = touch.clientY
  touchStartAt = Date.now()
  dragOffset.value = 0
}

function onTouchMove(event: any) {
  const touch = event.touches?.[0]
  if (!touch || !dragging.value) return
  let delta = touch.clientY - touchStartY
  const atStart = activeIndex.value === 0 && delta > 0
  const atEnd = activeIndex.value === props.cards.length - 1 && delta < 0
  if (atStart || atEnd) delta *= 0.28
  dragOffset.value = Math.max(-180, Math.min(180, delta))
  if (Math.abs(delta) > 4) suppressTapUntil = Date.now() + 280
}

function onTouchEnd(event: any) {
  if (!dragging.value) return
  const changedTouch = event.changedTouches?.[0]
  const rawDelta = changedTouch ? changedTouch.clientY - touchStartY : dragOffset.value
  const elapsed = Math.max(Date.now() - touchStartAt, 1)
  const velocity = rawDelta / elapsed
  const shouldMove = Math.abs(rawDelta) >= 48 || Math.abs(velocity) >= 0.45
  dragging.value = false
  dragOffset.value = 0
  if (!shouldMove) return
  if (rawDelta < 0) selectIndex(activeIndex.value + 1)
  else selectIndex(activeIndex.value - 1)
}

function onCardTap(index: number) {
  if (Date.now() < suppressTapUntil) return
  if (index !== activeIndex.value) {
    selectIndex(index)
    return
  }
  confirmActive()
}

function confirmActive() {
  const card = activeCard.value
  if (!card || card.state === 'loading') return
  if (card.state === 'error') {
    emit('retry', card.key)
    return
  }
  emit('confirm', card.key)
}

function close() {
  emit('close')
}

function setScrollLocked(locked: boolean) {
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
    confirmActive()
  } else if (event.key === 'Escape') {
    event.preventDefault()
    close()
  }
}

watch(() => props.activeKey, (key) => {
  if (key) syncActiveKey(key)
})

watch(() => props.open, async (open) => {
  if (open) {
    updateViewport()
    syncActiveKey(props.activeKey)
    setScrollLocked(true)
    setTabBarHidden(true)
    await nextTick()
    // #ifdef H5
    document.querySelector<HTMLElement>('.fullscreen-card-navigator')?.focus()
    // #endif
  } else {
    setScrollLocked(false)
    setTabBarHidden(false)
  }
}, { immediate: true })

onMounted(() => {
  updateViewport()
  // #ifdef H5
  window.addEventListener('keydown', onKeydown)
  motionMedia = window.matchMedia('(prefers-reduced-motion: reduce)')
  reduceMotion.value = motionMedia.matches
  const onMotionChange = (event: MediaQueryListEvent) => { reduceMotion.value = event.matches }
  motionMedia.addEventListener?.('change', onMotionChange)
  ;(motionMedia as any)._wodListener = onMotionChange
  // #endif
})

onBeforeUnmount(() => {
  setScrollLocked(false)
  if (props.open) setTabBarHidden(false)
  // #ifdef H5
  window.removeEventListener('keydown', onKeydown)
  const listener = (motionMedia as any)?._wodListener
  if (listener) motionMedia?.removeEventListener?.('change', listener)
  // #endif
})
</script>

<style lang="scss" scoped>
.fullscreen-card-navigator {
  position: fixed;
  inset: 0;
  z-index: 10000;
  min-height: 100vh;
  min-height: 100dvh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  color: #f6fbfc;
  touch-action: none;
  outline: none;
  animation: overlay-in 260ms ease both;
}
.overlay-surface {
  position: absolute;
  inset: 0;
  background: rgba(7, 19, 29, 0.9);
  backdrop-filter: blur(12px) saturate(120%);
  -webkit-backdrop-filter: blur(12px) saturate(120%);
}
.navigator-header {
  position: relative;
  z-index: 40;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: calc(28rpx + var(--safe-top)) 32rpx 16rpx;
  background: linear-gradient(180deg, rgba(7, 19, 29, 1) 0%, rgba(7, 19, 29, 0.94) 72%, rgba(7, 19, 29, 0) 100%);
}
.header-copy { min-width: 0; padding-right: 24rpx; }
.navigator-title { display: block; color: #fff; font-size: 36rpx; font-weight: 750; letter-spacing: -0.5rpx; }
.navigator-subtitle { display: block; color: rgba(236, 247, 249, 0.66); font-size: 22rpx; margin-top: 8rpx; }
.close-button {
  min-width: 88rpx;
  min-height: 72rpx;
  padding: 0 22rpx;
  border: 1rpx solid rgba(255, 255, 255, 0.24);
  border-radius: 16rpx;
  background: rgba(255, 255, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 24rpx;
}
.close-button:active { transform: scale(0.98); }
.card-stage { position: relative; z-index: 20; flex: 1; min-height: 0; overflow: hidden; }
.navigator-card {
  position: absolute;
  left: 50%;
  top: 50%;
  width: min(86vw, 680rpx);
  min-height: 430rpx;
  box-sizing: border-box;
  overflow: hidden;
  border: 1rpx solid rgba(24, 175, 196, 0.3);
  border-radius: 28rpx;
  padding: 34rpx;
  background: var(--overlay-card-bg);
  color: var(--overlay-card-text);
  box-shadow: 0 28rpx 80rpx rgba(0, 9, 17, 0.28);
  transition: transform 300ms cubic-bezier(0.2, 0.76, 0.24, 1), opacity 220ms ease;
  will-change: transform, opacity;
}
.navigator-card.dragging { transition: none; }
.navigator-card.active { border-color: rgba(24, 175, 196, 0.72); }
.navigator-card.adjacent { filter: saturate(0.72); }
.card-accent { position: absolute; left: 0; top: 36rpx; bottom: 36rpx; width: 6rpx; border-radius: 0 6rpx 6rpx 0; background: #18afc4; }
.card-head { display: flex; align-items: flex-start; gap: 22rpx; }
.card-icon { width: 72rpx; height: 72rpx; border-radius: 18rpx; background: rgba(24, 175, 196, 0.11); color: #1599ab; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.card-heading { min-width: 0; flex: 1; }
.card-title { display: block; color: var(--overlay-card-text); font-size: 36rpx; font-weight: 760; line-height: 1.25; }
.card-description { display: block; color: var(--overlay-card-sub); font-size: 23rpx; line-height: 1.45; margin-top: 8rpx; }
.metric-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); margin-top: 36rpx; }
.metric-item { min-width: 0; padding: 0 12rpx; text-align: center; }
.metric-item + .metric-item { border-left: 1rpx solid rgba(118, 139, 146, 0.2); }
.metric-value { display: block; color: var(--overlay-card-text); font-size: 30rpx; font-weight: 780; font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.metric-value.positive { color: #15803d; }
.metric-value.warning { color: #b45309; }
.metric-value.danger { color: #dc2626; }
.metric-label { display: block; color: var(--overlay-card-muted); font-size: 20rpx; line-height: 1.35; margin-top: 8rpx; }
.metric-item:nth-child(n + 4) { margin-top: 24rpx; }
.metric-item:nth-child(4) { border-left: 0; }
.card-footer { display: flex; align-items: center; justify-content: flex-end; gap: 16rpx; margin-top: 36rpx; }
.card-footnote { flex: 1; color: var(--overlay-card-muted); font-size: 20rpx; line-height: 1.4; }
.card-action { min-height: 72rpx; padding: 0 24rpx; border-radius: 16rpx; background: #147f8f; color: #fff; display: inline-flex; align-items: center; justify-content: center; gap: 8rpx; font-size: 24rpx; font-weight: 650; white-space: nowrap; }
.card-action:active { transform: scale(0.98); }
.card-state { min-height: 158rpx; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 20rpx; }
.state-title { color: var(--overlay-card-sub); font-size: 24rpx; text-align: center; }
.state-action { min-height: 64rpx; padding: 0 24rpx; border: 1rpx solid rgba(24, 175, 196, 0.45); border-radius: 16rpx; color: #147f8f; display: flex; align-items: center; font-size: 23rpx; }
.skeleton-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18rpx; margin-top: 42rpx; }
.skeleton-metric { display: flex; flex-direction: column; align-items: center; gap: 12rpx; }
.skeleton-line { border-radius: 8rpx; background: linear-gradient(90deg, #e8edef, #f5f7f8, #e8edef); background-size: 200% 100%; animation: skeleton-shift 1.2s ease infinite; }
.skeleton-line.value { width: 84rpx; height: 36rpx; }
.skeleton-line.label { width: 108rpx; height: 20rpx; }
.navigator-footer { position: relative; z-index: 40; display: flex; align-items: center; justify-content: center; gap: 18rpx; padding: 14rpx 32rpx calc(32rpx + var(--safe-bottom)); }
.position-label { color: #fff; font-size: 22rpx; font-variant-numeric: tabular-nums; }
.gesture-hint { color: rgba(236, 247, 249, 0.65); font-size: 22rpx; }

@keyframes overlay-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes skeleton-shift { from { background-position: 100% 0; } to { background-position: -100% 0; } }

@media (prefers-reduced-motion: reduce) {
  .fullscreen-card-navigator { animation-duration: 80ms; }
  .navigator-card { transition-duration: 80ms; }
  .skeleton-line { animation: none; }
}

@media (prefers-reduced-transparency: reduce) {
  .overlay-surface { background: #0b1821; backdrop-filter: none; -webkit-backdrop-filter: none; }
}

@media (orientation: landscape) {
  .navigator-card { min-height: 300rpx; padding: 24rpx 32rpx; }
  .metric-grid { margin-top: 22rpx; }
  .card-footer { margin-top: 22rpx; }
}
</style>
