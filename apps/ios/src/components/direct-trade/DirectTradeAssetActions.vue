<template>
  <view class="direct-asset-actions">
    <view v-if="asset.can_sell" class="action sell" :class="{ disabled: submitting }" @tap="sell">{{ t(submitting ? '处理中...' : 'sell') }}</view>
    <view v-else-if="asset.purchase_type === 'usage'" class="action primary" @tap="renew">{{ t('renew') }}</view>
    <view v-else class="action disabled">{{ asset.trading_unavailable_reason ? tr(asset.trading_unavailable_reason) : t('holdingTradingUnavailable') }}</view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { sellAsset, type AssetItem } from '@/api/asset'
import { formatCardHourCurrency } from '@/utils/format'
import { navigateBack, navigateTo as nav } from '@/utils/nav'
import { useI18nStore } from '@/store/i18n'

const props = defineProps<{ asset: AssetItem }>()
const { t, tr } = useI18nStore()
const submitting = ref(false)
const pendingRequestId = ref('')
const pendingSignature = ref('')

function requestId() {
  const signature = `${props.asset.id}:${props.asset.current_unit_price ?? 0}`
  if (!pendingRequestId.value || pendingSignature.value !== signature) {
    pendingSignature.value = signature
    pendingRequestId.value = `asset-sale-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
  }
  return pendingRequestId.value
}

function sell() {
  if (submitting.value || !props.asset.can_sell || !props.asset.current_unit_price) return
  const pnl = props.asset.pnl ?? 0
  const sellPrice = props.asset.current_price ?? 0
  uni.showModal({
    title: t('确认出售'),
    content: `${t('k_87165f6a')}: ${formatCardHourCurrency(sellPrice)}\n${t('k_a8401d10')}: ${pnl >= 0 ? '+' : ''}${formatCardHourCurrency(pnl)}\n\n${t('确认按当前市价出售？')}`,
    confirmText: t('确认出售'),
    success: async result => {
      if (!result.confirm) return
      submitting.value = true
      try {
        const response = await sellAsset(props.asset.id, props.asset.current_unit_price!, requestId())
        pendingRequestId.value = ''
        pendingSignature.value = ''
        uni.showToast({ title: `${t('出售成功')} ${t(response.pnl >= 0 ? '盈利' : '亏损')}${formatCardHourCurrency(response.pnl)}`, icon: 'none' })
        setTimeout(() => navigateBack(), 1000)
      } finally {
        submitting.value = false
      }
    },
  })
}

function renew() {
  if (props.asset.product_id) nav(`/pages/product/detail?id=${props.asset.product_id}`)
}
</script>

<style scoped>
.direct-asset-actions { width: 100%; }
.action { width: 100%; min-height: 80rpx; display: flex; align-items: center; justify-content: center; border-radius: var(--radius); font-size: 28rpx; font-weight: 700; }
.action.primary { color: #fff; background: var(--primary); }
.action.sell { color: var(--down); border: 1rpx solid var(--down); }
.action.disabled { color: var(--text-dim); background: var(--bg-2); }
</style>
