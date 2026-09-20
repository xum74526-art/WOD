<template>
  <view v-if="restartRoute" class="restart-action" @tap="restart">{{ t('restartRecharge') }}</view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RechargePaymentOrder } from '@/api/wallet'
import { createRechargeRestartRoute } from '@/utils/recharge-payment'
import { navigateTo as nav } from '@/utils/nav'
import { useI18nStore } from '@/store/i18n'

const props = defineProps<{ order: RechargePaymentOrder }>()
const { t } = useI18nStore()
const restartRoute = computed(() => createRechargeRestartRoute(props.order))
function restart() { if (restartRoute.value) nav(restartRoute.value) }
</script>

<style scoped>
.restart-action { min-height: 60rpx; padding: 0 20rpx; display: flex; align-items: center; justify-content: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: 14rpx; font-size: 22rpx; font-weight: 700; }
</style>
