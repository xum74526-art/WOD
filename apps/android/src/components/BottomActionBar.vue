<template>
  <view class="bar" :style="{ paddingBottom: 'calc(16rpx + var(--safe-bottom))' }">
    <slot />
  </view>
</template>

<style lang="scss" scoped>
.bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--bg-2);
  border-top: 1rpx solid var(--border);
  padding: 16rpx 32rpx;
  z-index: 100;
}
</style>
