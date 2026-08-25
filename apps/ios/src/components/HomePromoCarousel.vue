<template>
  <view class="home-promo" :aria-label="t('homePromoRegionLabel')">
    <view class="promo-stage">
      <swiper
        class="promo-swiper"
        :current="currentIndex"
        :autoplay="autoplayEnabled"
        :interval="5200"
        :duration="420"
        circular
        :indicator-dots="false"
        @change="onSlideChange"
      >
        <swiper-item v-for="slide in HOME_PROMOTIONS" :key="slide.id">
          <view
            class="promo-card"
            :class="`promo-card--${slide.id}`"
            role="button"
            :aria-label="`${t(slide.titleKey)}，${t(slide.actionKey)}`"
            @tap="openItem(slide)"
          >
            <image
              class="promo-background"
              :class="`promo-background--${slide.id}`"
              :src="slide.image"
              mode="aspectFill"
              :aria-label="t(slide.imageAltKey)"
            />
            <view class="promo-shade" aria-hidden="true" />
            <view class="promo-copy">
              <text class="promo-kicker">{{ t(slide.kickerKey) }}</text>
              <text class="promo-title">{{ t(slide.titleKey) }}</text>
              <text class="promo-description">{{ t(slide.descriptionKey) }}</text>
              <view class="promo-action">
                <text>{{ t(slide.actionKey) }}</text>
              </view>
            </view>
          </view>
        </swiper-item>
      </swiper>

      <view class="promo-inline-controls" :aria-label="t('homeCarouselStatus')">
        <view
          class="promo-page-button promo-page-button--previous"
          role="button"
          :aria-label="t('homeCarouselPrevious')"
          @tap.stop="previousSlide"
        >
          <AppIcon name="arrow-left" :size="25" />
        </view>
        <view class="promo-dots" aria-hidden="true">
          <view
            v-for="(slide, index) in HOME_PROMOTIONS"
            :key="slide.id"
            class="promo-dot"
            :class="{ active: currentIndex === index }"
          />
        </view>
        <view
          class="promo-page-button promo-page-button--next"
          role="button"
          :aria-label="t('homeCarouselNext')"
          @tap.stop="nextSlide"
        >
          <AppIcon name="arrow-right" :size="25" />
        </view>
      </view>
    </view>

    <view class="notice-bar">
      <view class="notice-icon" aria-hidden="true">
        <AppIcon name="bell" :size="29" />
      </view>
      <text class="notice-label">{{ t('homeNoticeLabel') }}</text>
      <swiper
        class="notice-swiper"
        vertical
        circular
        :autoplay="autoplayEnabled"
        :interval="3800"
        :duration="340"
        :indicator-dots="false"
      >
        <swiper-item v-for="notice in HOME_NOTICES" :key="notice.id">
          <view
            class="notice-item"
            role="button"
            :aria-label="t(notice.textKey)"
            @tap="openItem(notice)"
          >
            <text class="notice-text">{{ t(notice.textKey) }}</text>
            <AppIcon class="notice-arrow" name="arrow-right" :size="24" />
          </view>
        </swiper-item>
      </swiper>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import { useI18nStore } from '@/store/i18n'
import { navigateTo } from '@/utils/nav'
import {
  HOME_NOTICES,
  HOME_PROMOTIONS,
  type HomePromotionNavigation,
} from '@/config/home-promotions'

const { t } = useI18nStore()
const currentIndex = ref(0)
const autoplayEnabled = ref(true)

onMounted(() => {
  // #ifdef H5
  if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
    autoplayEnabled.value = false
  }
  // #endif
})

function onSlideChange(event: { detail?: { current?: number } }) {
  const next = Number(event.detail?.current)
  if (Number.isInteger(next) && next >= 0 && next < HOME_PROMOTIONS.length) currentIndex.value = next
}

function previousSlide() {
  currentIndex.value = (currentIndex.value - 1 + HOME_PROMOTIONS.length) % HOME_PROMOTIONS.length
}

function nextSlide() {
  currentIndex.value = (currentIndex.value + 1) % HOME_PROMOTIONS.length
}

function openItem(item: { route: string; navigation: HomePromotionNavigation }) {
  if (item.navigation === 'switchTab') {
    uni.switchTab({ url: item.route })
    return
  }
  navigateTo(item.route)
}
</script>

<style lang="scss" scoped>
.home-promo {
  width: 100%;
  margin: 4rpx 0 26rpx;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'PingFang SC', 'HarmonyOS Sans', 'Microsoft YaHei', sans-serif;
}

.promo-stage {
  position: relative;
  width: 100%;
  height: 390rpx;
}
.promo-swiper { width: 100%; height: 390rpx; }
.promo-card {
  position: relative;
  isolation: isolate;
  display: flex;
  align-items: stretch;
  width: 100%;
  height: 390rpx;
  overflow: hidden;
  box-sizing: border-box;
  border: 1rpx solid rgba(149, 226, 235, 0.14);
  border-radius: 34rpx;
  background: #081A20;
  box-shadow: 0 14rpx 32rpx rgba(12, 57, 65, 0.16);
}
.promo-card:active { transform: scale(0.99); }
.promo-background {
  position: absolute;
  inset: 0;
  z-index: 0;
  width: 100%;
  height: 100%;
  opacity: 0.96;
}
.promo-background--market { opacity: 0.88; }
.promo-background--wallet { opacity: 0.82; }
.promo-shade {
  position: absolute;
  inset: 0;
  z-index: 1;
  background:
    linear-gradient(90deg, rgba(4, 18, 23, 0.98) 0%, rgba(4, 18, 23, 0.94) 34%, rgba(4, 18, 23, 0.54) 60%, rgba(4, 18, 23, 0.08) 100%),
    linear-gradient(0deg, rgba(2, 12, 15, 0.56) 0%, rgba(2, 12, 15, 0) 58%);
}
.promo-copy {
  position: relative;
  z-index: 2;
  display: flex;
  width: 59%;
  min-width: 0;
  flex-direction: column;
  justify-content: center;
  box-sizing: border-box;
  padding: 40rpx 12rpx 42rpx 42rpx;
}
.promo-kicker {
  color: #8EDDE7;
  font-size: 12px;
  font-weight: 800;
  line-height: 1.35;
}
.promo-title {
  display: block;
  max-width: 390rpx;
  margin-top: 10rpx;
  color: #F4FCFD;
  font-size: 22px;
  font-weight: 800;
  line-height: 1.16;
  letter-spacing: -0.25px;
}
.promo-description {
  display: block;
  max-width: 380rpx;
  margin-top: 13rpx;
  color: #BDE9EE;
  font-size: 13px;
  line-height: 1.5;
  opacity: 0.94;
}
.promo-action {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  min-height: 62rpx;
  margin-top: 20rpx;
  padding: 0 22rpx;
  border: 1rpx solid rgba(255, 255, 255, 0.24);
  border-radius: 16rpx;
  background: #8EDDE7;
  color: #07323A;
  font-size: 12px;
  font-weight: 800;
  white-space: nowrap;
  box-shadow: inset 0 1rpx 0 rgba(255, 255, 255, 0.54);
}

.promo-inline-controls {
  position: absolute;
  right: 12px;
  bottom: 12px;
  z-index: 4;
  display: flex;
  align-items: center;
  gap: 4px;
}
.promo-dots { display: flex; align-items: center; }
.promo-dots { gap: 5px; padding: 0 5px; }
.promo-page-button {
  display: flex;
  width: 44px;
  height: 44px;
  align-items: center;
  justify-content: center;
  border: 1rpx solid rgba(190, 239, 244, 0.28);
  border-radius: 14px;
  background: rgba(5, 23, 28, 0.74);
  color: #D8F9FC;
  box-shadow: inset 0 1rpx 0 rgba(255, 255, 255, 0.12);
}
.promo-page-button:active { transform: scale(0.96); background: rgba(142, 221, 231, 0.24); color: #FFFFFF; }
.promo-dot {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: rgba(216, 249, 252, 0.42);
  transition: width 0.24s ease, background-color 0.24s ease;
}
.promo-dot.active { width: 16px; background: #8EDDE7; }

.notice-bar {
  display: flex;
  height: 88rpx;
  align-items: center;
  overflow: hidden;
  margin-top: 16rpx;
  padding: 0 16rpx;
  border: 1rpx solid var(--card-border);
  border-radius: 28rpx;
  background: var(--card);
  box-shadow: var(--shadow);
}
.notice-icon {
  display: flex;
  width: 44rpx;
  height: 44rpx;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  border-radius: 14rpx;
  background: var(--primary-soft);
  color: var(--primary);
}
.notice-label {
  flex-shrink: 0;
  margin-left: 12rpx;
  color: var(--primary);
  font-size: 12px;
  font-weight: 700;
}
.notice-swiper { height: 88rpx; min-width: 0; flex: 1; margin-left: 14rpx; }
.notice-item { display: flex; height: 88rpx; min-width: 0; align-items: center; gap: 8rpx; }
.notice-text {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  color: var(--text);
  font-size: 12px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.notice-arrow { flex-shrink: 0; color: var(--text-sub); }

@media (max-width: 360px) {
  .promo-stage,
  .promo-swiper,
  .promo-card { height: 410rpx; }
  .promo-copy { width: 64%; padding: 30rpx 8rpx 38rpx 30rpx; }
  .promo-title { font-size: 20px; }
  .promo-description { font-size: 12px; }
  .promo-inline-controls { right: 10px; bottom: 10px; }
  .promo-page-button { width: 40px; height: 40px; border-radius: 12px; }
  .notice-label { display: none; }
  .notice-swiper { margin-left: 12rpx; }
}

@media (prefers-reduced-motion: reduce) {
  .promo-card:active { transform: none; }
  .promo-page-button:active { transform: none; }
  .promo-dot { transition: none; }
}
</style>
