<template>
  <view class="redirect-page"></view>
</template>

<script setup lang="ts">
import { onLoad } from '@dcloudio/uni-app'

onLoad(() => {
  uni.redirectTo({ url: '/pages/buy-request/index' })
})
</script>

<style scoped>
.redirect-page { min-height: 100vh; background: var(--bg); }
</style>
