<template>
  <view class="direct-checkout">
    <view class="buy-btn" :class="{ disabled: submitting || disabled }" @tap="openConfirm">
      {{ t(submitting ? '处理中...' : (disabled ? 'viewDetail' : (purchaseType === 'holding' ? 'buyHolding' : 'k_25575fc0'))) }}
    </view>
    <ConfirmSheet
      :visible="showConfirm"
      :title="t(purchaseType === 'holding' ? 'confirmHoldingPurchase' : 'confirmUsagePurchase')"
      :desc="`${localizeProductName(product.name, i18n.lang)} × ${quantity}，${t('hoursValue', { count: hours })}，${fmtCardHours(totalCardHours)} ${t('cardHour')}`"
      :confirmText="t('k_936de2c4')"
      @cancel="cancelConfirm"
      @confirm="submitOrder"
    >
      <view class="confirm-fee">
        <text>{{ t('k_99b6bb88') }}</text>
        <text class="confirm-value">{{ fmtCardHours(totalCardHours) }} {{ t('cardHour') }}</text>
      </view>
      <view v-if="purchaseType === 'usage'" class="confirm-fee rebate-row">
        <text>{{ t('estimatedExpiryRebate') }}</text>
        <text class="confirm-value">{{ fmtCardHours(estimatedRebate || 0) }} {{ t('cardHour') }}<template v-if="estimatedRebateRate"> · {{ estimatedRebateRate }}%</template></text>
      </view>
      <text v-if="purchaseType === 'usage'" class="confirm-note">{{ t('rebateEstimateCheckoutNotice') }}</text>
      <text v-else class="confirm-note">{{ t('holdingRisk') }}</text>
    </ConfirmSheet>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { createOrder } from '@/api/order'
import type { PurchaseType } from '@/api/order'
import type { Product } from '@/api/gpu'
import ConfirmSheet from '@/components/ConfirmSheet.vue'
import { directTradeCardHoursPerGpuHour } from '@/utils/direct-trade'
import { fmtCardHours } from '@/utils/format'
import { localizeProductName } from '@/utils/localize-content'
import { navigateTo as nav } from '@/utils/nav'
import { useI18nStore } from '@/store/i18n'

const props = defineProps<{
  product: Product
  hours: number
  quantity: number
  purchaseType: PurchaseType
  estimatedRebate?: number
  estimatedRebateRate?: number
  disabled?: boolean
  unavailableMessage?: string
}>()

const i18n = useI18nStore()
const { t } = i18n
const showConfirm = ref(false)
const submitting = ref(false)
const pendingRequestId = ref('')
const pendingRequestSignature = ref('')
const pricePerGpuHour = computed(() => directTradeCardHoursPerGpuHour(props.product))
const totalCardHours = computed(() => pricePerGpuHour.value * props.hours * props.quantity)

function ensureRequestId(): string {
  const signature = `${props.product.id}:${props.hours}:${props.quantity}:${props.purchaseType}:${pricePerGpuHour.value}`
  if (!pendingRequestId.value || pendingRequestSignature.value !== signature) {
    pendingRequestSignature.value = signature
    pendingRequestId.value = `wod-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
  }
  return pendingRequestId.value
}

function openConfirm() {
  if (props.disabled) {
    uni.showToast({ title: props.unavailableMessage || t('marketOfferUnavailableShort'), icon: 'none' })
    return
  }
  ensureRequestId()
  showConfirm.value = true
}

function cancelConfirm() {
  showConfirm.value = false
  pendingRequestId.value = ''
  pendingRequestSignature.value = ''
}

async function submitOrder() {
  showConfirm.value = false
  if (submitting.value || props.disabled) return
  submitting.value = true
  try {
    const created = await createOrder(
      props.product.id,
      props.hours,
      props.purchaseType,
      props.quantity,
      ensureRequestId(),
      pricePerGpuHour.value,
    )
    pendingRequestId.value = ''
    pendingRequestSignature.value = ''
    uni.showToast({ title: t('购买成功'), icon: 'success' })
    setTimeout(() => nav(`/pages/order/detail?id=${created.id}`), 800)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.direct-checkout { width: 100%; }
.buy-btn { width: 100%; height: 88rpx; display: flex; align-items: center; justify-content: center; color: #fff; background: var(--primary); border-radius: var(--radius); font-size: 30rpx; font-weight: 700; }
.buy-btn.disabled { opacity: 0.45; }
.confirm-fee { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; color: var(--text-sub); }
.confirm-value { color: var(--up); font-weight: 700; }
.rebate-row { margin-top: 18rpx; }
.confirm-note { display: block; margin-top: 18rpx; color: var(--text-sub); font-size: 22rpx; line-height: 1.55; }
</style>
