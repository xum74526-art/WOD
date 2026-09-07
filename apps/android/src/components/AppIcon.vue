<template>
  <view class="icon" :style="{ width: size + 'rpx', height: size + 'rpx' }" v-html="svg"></view>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ name: string; size?: number; color?: string }>(), {
  size: 24,
  color: '',
})

// 每个业务图标使用独立轮廓，避免同一角色页面出现“图标相同但含义不同”。
const PATHS: Record<string, string> = {
  'arrow-right': 'M9 6l6 6-6 6',
  'arrow-left': 'M15 6L9 12l6 6',
  'chevron-down': 'M6 9l6 6 6-6',
  bell: 'M12 4a4 4 0 014 4v4l2 3H6l2-3V8a4 4 0 014-4zM10 19a2 2 0 004 0',
  wallet: 'M4 7h13a2 2 0 012 2v8a2 2 0 01-2 2H6a2 2 0 01-2-2V7zm0 0V6a2 2 0 012-2h9',
  order: 'M5 4h14v16H5zM8 8h8M8 12h8M8 16h5',
  revenue: 'M4 16l4-5 4 3 4-6 4 4',
  settings: 'M12 8a4 4 0 100 8 4 4 0 000-8zM12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2',
  help: 'M12 22a10 10 0 100-20 10 10 0 000 20zM9.5 9a2.5 2.5 0 015 0c0 2.5-2.5 2-2.5 4M12 17h.01',
  mail: 'M3 5h18v14H3zM3 7l9 7 9-7',
  shield: 'M12 3l8 3v6c0 4-3 7-8 9-5-2-8-5-8-9V6l8-3z',
  plus: 'M12 5v14M5 12h14',
  minus: 'M5 12h14',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 100 6 3 3 0 000-6z',
  check: 'M5 12l5 5 9-11',
  refresh: 'M4 12a8 8 0 0114-5M20 12a8 8 0 01-14 5M20 4v5h-5M4 20v-5h5',
  search: 'M11 4a7 7 0 100 14 7 7 0 000-14zM21 21l-5-5',
  filter: 'M4 5h16l-6 7v6l-4 2v-8z',
  chevron: 'M9 6l6 6-6 6',
  gpu: 'M4 8h16v8H4zM8 12h8M12 4v4M12 16v4',
  user: 'M12 12a4 4 0 100-8 4 4 0 000 8zM4 20a8 8 0 0116 0',
  logout: 'M9 4H6a2 2 0 00-2 2v12a2 2 0 002 2h3M15 4l5 8-5 8M20 12H9',
  heart: 'M12 21s-7-4.5-9.5-8.5C1 9 2.5 5.5 6 5.5c2 0 3.5 1 6 3.5 2.5-2.5 4-3.5 6-3.5 3.5 0 5 3.5 3.5 7C19 16.5 12 21 12 21z',
  share: 'M4 12v8a1 1 0 001 1h14a1 1 0 001-1v-8M16 6l-4-4-4 4M12 2v13',
  comment: 'M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2v10z',
  coin: 'M12 2a10 10 0 100 20 10 10 0 000-20zM12 7v10M9.5 9.5c0-1 1.1-1.8 2.5-1.8s2.5.8 2.5 1.8-1.1 1.5-2.5 1.5-2.5.5-2.5 1.5 1.1 1.8 2.5 1.8 2.5-.8 2.5-1.8',
  friends: 'M9 11a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM17.5 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM3 21a6 6 0 0112 0M15 21a5 5 0 016.7-4.7',
  // 设备/服务器
  device: 'M5 4h14v6H5zM5 12h14v6H5zM8 7h.01M8 15h.01',
  // 邀请好友
  invite: 'M9 11a4 4 0 100-8 4 4 0 000 8zM2 21a7 7 0 0114 0M19 7v6M16 10h6',
  // 银行卡
  'bank-card': 'M3 6h18v12H3zM3 10h18M7 15h4',
  // 实名认证
  verified: 'M4 5h16v14H4zM8 9a2 2 0 100-4 2 2 0 000 4zM6 16a3 3 0 016 0M14 11l2 2 4-4',
  // 采购
  procurement: 'M3 4h2l2 11h10l3-8H6M9 20h.01M17 20h.01',
  // 优惠券
  coupon: 'M4 7h16v10H4zM8 7v10',
  // 地址管理
  address: 'M12 2a7 7 0 00-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 00-7-7zM12 9a2 2 0 100 4 2 2 0 000-4z',
  // 算力入驻
  onboarding: 'M4 8h10v8H4zM7 12h4M7 4v4M7 16v4M18 5v6M15 8h6',
  // 在线客服
  'online-service': 'M4 13v-2a8 8 0 0116 0v2M4 13h3v5H5a1 1 0 01-1-1v-4zM20 13h-3v5h2a1 1 0 001-1v-4zM17 18c0 2-2 3-5 3',
  // 人工客服
  'manual-service': 'M8 10a4 4 0 108 0 4 4 0 00-8 0zM4 21a8 8 0 0116 0M18 4h4v4M18 8l4-4',
}

const svg = computed(() => {
  const p = PATHS[props.name] || PATHS['arrow-right']
  return `<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${p}"/></svg>`
})
</script>

<style scoped>
.icon { display: inline-flex; align-items: center; justify-content: center; color: v-bind('props.color || "inherit"'); }
</style>
