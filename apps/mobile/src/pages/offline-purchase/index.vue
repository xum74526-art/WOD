<template>
  <view class="redirect-page"></view>
</template>

<script setup lang="ts">
import { onLoad } from '@dcloudio/uni-app'
import { isDirectCommerceEnabled } from '@/utils/ios-distribution'

onLoad(() => {
  if (!isDirectCommerceEnabled()) {
    uni.switchTab({ url: '/pages/profile/index' })
    return
  }
  uni.redirectTo({ url: '/pages/buy-request/index' })
})
</script>

<style scoped>
.redirect-page { min-height: 100vh; background: var(--bg); }
</style>
