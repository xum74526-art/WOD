<template>
  <view class="navbar" :style="{ paddingTop: 'var(--safe-top)' }">
    <view class="nb-inner">
      <view class="nb-left" @tap="onBack" v-if="showBack">
        <AppIcon name="arrow-left" :size="44" />
      </view>
      <view class="nb-left" v-else><slot name="left" /></view>
      <text class="nb-title">{{ t(title) }}</text>
      <view class="nb-right">
        <slot name="right" />
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import { navigateBack } from '@/utils/nav'
import { useI18nStore } from '@/store/i18n'

const { t } = useI18nStore()

withDefaults(defineProps<{ title?: string; showBack?: boolean }>(), {
  title: '',
  showBack: true,
})

function onBack() {
  navigateBack()
}
</script>

<style lang="scss" scoped>
.navbar {
  position: sticky;
  top: 0;
  z-index: 50;
  background: var(--nav-bg);
  border-bottom: 1rpx solid var(--divider);
  transition: background 0.3s, border-color 0.3s;
}
.nb-inner {
  height: 88rpx;
  display: grid;
  grid-template-columns: minmax(88rpx, 1fr) minmax(0, auto) minmax(88rpx, 1fr);
  align-items: center;
  padding: 0 24rpx;
}
.nb-left {
  grid-column: 1;
  justify-self: start;
  min-width: 88rpx;
  height: 88rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text);
}
.nb-title {
  grid-column: 2;
  min-width: 0;
  max-width: 100%;
  text-align: center;
  color: var(--text);
  font-size: 32rpx;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.nb-right {
  grid-column: 3;
  justify-self: end;
  width: auto;
  min-width: 88rpx;
  height: 88rpx;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  white-space: nowrap;
}
</style>
