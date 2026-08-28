<template>
  <view class="direct-wallet-actions">
    <view class="action-row">
      <view class="action ghost" :class="{ disabled: !commerce.rechargeEnabled }" @tap="openRecharge">{{ t('recharge') }}</view>
      <view class="action primary" :class="{ disabled: !commerce.withdrawEnabled || !wallet?.withdraw_service_enabled }" @tap="openWithdraw">{{ t('withdraw') }}</view>
    </view>

    <view v-if="sheet.type === 'recharge'" class="mask" @tap="closeSheet">
      <view class="sheet" @tap.stop>
        <text class="sheet-title">{{ t('k_2d1872ca') }}</text>
        <view class="rate-card">
          <text>{{ t('rechargeRateLockedHint') }}</text>
          <text>1 {{ t('cardHour') }} = {{ formatNumber(cardHourRate, { maximumFractionDigits: 3 }) }} {{ t('cny') }}</text>
        </view>
        <view class="input-wrap"><text>¥</text><input v-model="sheet.amount" type="digit" :placeholder="t('enterRechargeCny')" /></view>
        <view class="quick-amounts">
          <view v-for="amount in quickAmounts" :key="amount" class="quick-amount" @tap="sheet.amount = String(amount)">¥{{ amount }}</view>
        </view>
        <view class="payment-methods">
          <view v-for="method in paymentMethods" :key="method.value" class="payment-method" :class="{ active: sheet.paymentType === method.value }" @tap="sheet.paymentType = method.value">
            {{ t(method.label) }}
          </view>
        </view>
        <text v-if="!rechargeEnabled" class="unavailable">{{ t('mapayKeyPending') }}</text>
        <view class="sheet-actions">
          <view class="sheet-button ghost" @tap="closeSheet">{{ t('cancel') }}</view>
          <view class="sheet-button primary" :class="{ disabled: !rechargeEnabled || submitting }" @tap="submitRecharge">{{ t(submitting ? 'submitting' : 'payAndRecharge') }}</view>
        </view>
      </view>
    </view>

    <view v-if="sheet.type === 'withdraw'" class="mask" @tap="closeSheet">
      <view class="sheet" @tap.stop>
        <text class="sheet-title">{{ t('k_1b3593c1') }}</text>
        <view v-if="!bankCards.length" class="empty-card">
          <text>{{ t('k_5cdf6123') }}</text>
          <view class="sheet-button primary" @tap="goBankCards">{{ t('k_e2f477a5') }}</view>
        </view>
        <template v-else>
          <view class="input-wrap"><text>{{ t('cardHour') }}</text><input v-model="sheet.amount" type="digit" :placeholder="t('withdrawableValue', { amount: `${fmtCardHours(wallet?.withdrawable_balance ?? 0)} ${t('cardHour')}` })" /></view>
          <picker :range="bankCards" range-key="displayName" :value="cardIndex" @change="onCardChange">
            <view class="picker-value">{{ bankCards[cardIndex]?.displayName || t('请选择银行卡') }}</view>
          </picker>
          <view class="withdraw-preview">
            <text>{{ t('estimatedArrival') }}</text>
            <text>¥{{ formatMoney(withdrawNet) }}</text>
          </view>
          <view class="sheet-actions">
            <view class="sheet-button ghost" @tap="closeSheet">{{ t('cancel') }}</view>
            <view class="sheet-button primary" :class="{ disabled: submitting }" @tap="submitWithdrawal">{{ t(submitting ? 'submitting' : 'submitWithdrawalRequest') }}</view>
          </view>
        </template>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { WalletInfo, RechargePaymentType } from '@/api/wallet'
import { createRechargePayment } from '@/api/wallet'
import { getBankCards, type BankCardItem } from '@/api/bank-card'
import { createWithdrawal, getWithdrawalConfig, type WithdrawalConfig } from '@/api/withdrawal'
import { isRegisteredBankCardStatus } from '@/utils/bank-card'
import { resolveBackendUrl } from '@/utils/config'
import { fmtCardHours, formatMoney, formatNumber } from '@/utils/format'
import { openPaymentCheckout } from '@/utils/payment-checkout'
import {
  DEFAULT_RECHARGE_TTL_SECONDS,
  effectiveRechargeMinimum,
  effectiveWithdrawalMinimum,
  MINIMUM_RECHARGE_CNY,
  readStoredRechargeSession,
  type RechargePrefill,
  type StoredRechargeSession,
} from '@/utils/recharge-payment'
import { navigateTo as nav } from '@/utils/nav'
import { useI18nStore } from '@/store/i18n'
import { useCommerceStore } from '@/store/commerce'

const props = defineProps<{
  wallet: WalletInfo | null
  rechargePrefill?: RechargePrefill | null
  openWithdrawal?: boolean
}>()
const emit = defineEmits<{ paymentStarted: []; walletUpdated: [] }>()
const { t } = useI18nStore()
const commerce = useCommerceStore()
const PENDING_PAYMENT_KEY = 'wod-pending-recharge-order'
const quickAmounts = [MINIMUM_RECHARGE_CNY, 50, 100]
const submitting = ref(false)
const withdrawConfig = ref<WithdrawalConfig | null>(null)
const bankCards = ref<Array<BankCardItem & { displayName: string }>>([])
const cardIndex = ref(0)
const consumedPrefill = ref(false)
const consumedWithdrawalIntent = ref(false)
const sheet = reactive<{ type: '' | 'recharge' | 'withdraw'; amount: string; paymentType: RechargePaymentType }>({
  type: '',
  amount: '',
  paymentType: 'alipay',
})
const allPaymentMethods: Array<{ value: RechargePaymentType; label: string }> = [
  { value: 'alipay', label: 'alipay' },
  { value: 'wxpay', label: 'wechatPay' },
]
const paymentMethods = computed(() => {
  const enabled = props.wallet?.payment_config?.payment_types || []
  return enabled.map(value => allPaymentMethods.find(item => item.value === value)).filter((item): item is (typeof allPaymentMethods)[number] => Boolean(item))
})
const rechargeEnabled = computed(() => commerce.rechargeEnabled
  && props.wallet?.recharge_service_enabled === true
  && props.wallet?.payment_config?.enabled === true
  && paymentMethods.value.length > 0)
const cardHourRate = computed(() => Number(props.wallet?.payment_config?.card_hour_rmb_rate || 1.002))
const minimumAmount = computed(() => effectiveRechargeMinimum(props.wallet?.payment_config?.min_amount_cny))
const maximumAmount = computed(() => Number(props.wallet?.payment_config?.max_amount_cny || 50_000))
const minimumWithdrawal = computed(() => effectiveWithdrawalMinimum(withdrawConfig.value?.min_card_hours))
const withdrawGross = computed(() => Math.max(0, Number(sheet.amount) || 0) * Number(withdrawConfig.value?.rate_cny_per_card_hour || 0))
const withdrawFee = computed(() => withdrawGross.value * Number(withdrawConfig.value?.fee_rate || 0))
const withdrawNet = computed(() => Math.max(0, withdrawGross.value - withdrawFee.value))

watch(() => props.rechargePrefill, prefill => {
  if (!prefill || consumedPrefill.value) return
  consumedPrefill.value = true
  openRecharge(prefill)
}, { immediate: true })

watch(() => props.openWithdrawal, requested => {
  if (!requested || consumedWithdrawalIntent.value) return
  consumedWithdrawalIntent.value = true
  void openWithdraw()
}, { immediate: true })

function currentSession(): StoredRechargeSession | null {
  return readStoredRechargeSession(uni.getStorageSync(PENDING_PAYMENT_KEY))
}

function openRecharge(prefill?: RechargePrefill | null) {
  if (!commerce.rechargeEnabled) {
    uni.showToast({ title: t('mapayKeyPending'), icon: 'none' })
    return
  }
  if (currentSession()) {
    uni.showModal({
      title: t('activeRechargeExistsTitle'),
      content: t('activeRechargeExists'),
      showCancel: false,
      confirmText: t('viewRechargeOrders'),
      success: result => { if (result.confirm) nav('/pages/wallet/recharges') },
    })
    return
  }
  sheet.type = 'recharge'
  sheet.amount = prefill?.amount || ''
  sheet.paymentType = prefill?.paymentType && paymentMethods.value.some(item => item.value === prefill.paymentType)
    ? prefill.paymentType
    : paymentMethods.value[0]?.value || 'alipay'
}

async function openWithdraw() {
  const [configResult, cardsResult] = await Promise.allSettled([getWithdrawalConfig(), getBankCards()])
  if (configResult.status === 'fulfilled') withdrawConfig.value = configResult.value
  if (cardsResult.status === 'fulfilled') {
    bankCards.value = cardsResult.value.filter(card => isRegisteredBankCardStatus(card.status)).map(card => ({
      ...card,
      displayName: `${t(card.bank_name)} (${card.card_number})`,
    }))
  }
  if (!commerce.withdrawEnabled || !props.wallet?.withdraw_service_enabled || withdrawConfig.value?.enabled !== true) {
    uni.showToast({ title: t('manualWithdrawalUnavailable'), icon: 'none' })
    return
  }
  sheet.type = 'withdraw'
  sheet.amount = ''
}

function closeSheet() { sheet.type = '' }
function onCardChange(event: { detail: { value: number } }) { cardIndex.value = Number(event.detail.value) || 0 }
function goBankCards() { closeSheet(); nav('/pages/bank-cards/index') }

async function submitRecharge() {
  const raw = String(sheet.amount || '').trim()
  const amount = Number(raw)
  if (!/^\d+(?:\.\d{1,2})?$/.test(raw) || !Number.isFinite(amount) || amount < minimumAmount.value || amount > maximumAmount.value) {
    uni.showToast({ title: t('invalidRechargeAmount', { min: formatMoney(minimumAmount.value), max: formatMoney(maximumAmount.value) }), icon: 'none' })
    return
  }
  if (!rechargeEnabled.value || submitting.value) {
    if (!rechargeEnabled.value) uni.showToast({ title: t('mapayKeyPending'), icon: 'none' })
    return
  }
  submitting.value = true
  try {
    const payment = await createRechargePayment(amount, sheet.paymentType)
    const checkoutUrl = resolveBackendUrl(payment.checkout_url)
    if (!checkoutUrl) throw new Error('invalid checkout url')
    const session: StoredRechargeSession = {
      version: 1,
      orderNo: payment.order_no,
      checkoutUrl,
      fallbackExpiresAtMs: Date.now() + Number(props.wallet?.payment_config?.checkout_ttl_seconds || DEFAULT_RECHARGE_TTL_SECONDS) * 1000,
      successNotified: false,
    }
    uni.setStorageSync(PENDING_PAYMENT_KEY, session)
    closeSheet()
    emit('paymentStarted')
    openPaymentCheckout(checkoutUrl, () => uni.showToast({ title: t('paymentStartFailed'), icon: 'none' }))
  } finally {
    submitting.value = false
  }
}

async function submitWithdrawal() {
  const amount = Number(sheet.amount)
  if (!Number.isFinite(amount) || amount < minimumWithdrawal.value || amount > Number(withdrawConfig.value?.max_card_hours || Infinity)) {
    uni.showToast({ title: t('withdrawAmountRange', { min: formatNumber(minimumWithdrawal.value), max: formatNumber(withdrawConfig.value?.max_card_hours || 0) }), icon: 'none' })
    return
  }
  if (amount > Number(props.wallet?.withdrawable_balance || 0)) {
    uni.showToast({ title: t('withdrawableBalanceInsufficient'), icon: 'none' })
    return
  }
  const card = bankCards.value[cardIndex.value]
  if (!card || submitting.value) return
  submitting.value = true
  try {
    const order = await createWithdrawal({
      amount_card_hours: amount,
      bank_card_id: card.id,
      client_request_id: `wd-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
    })
    closeSheet()
    emit('walletUpdated')
    uni.showToast({ title: t('withdrawalSubmitted'), icon: 'success' })
    nav(`/pages/withdrawals/detail?id=${order.id}`)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.action-row { display: flex; gap: 16rpx; margin-top: 32rpx; }
.action, .sheet-button { flex: 1; min-height: 76rpx; display: flex; align-items: center; justify-content: center; border-radius: var(--radius); font-size: 28rpx; font-weight: 700; }
.primary { color: #fff; background: var(--primary); }
.ghost { color: var(--primary); border: 1rpx solid var(--primary); }
.disabled { opacity: 0.45; }
.mask { position: fixed; inset: 0; z-index: 999; display: flex; align-items: flex-end; background: rgba(0, 0, 0, 0.48); }
.sheet { width: 100%; padding: 34rpx 32rpx calc(34rpx + var(--safe-bottom)); background: var(--bg); border-radius: 30rpx 30rpx 0 0; }
.sheet-title { display: block; margin-bottom: 24rpx; color: var(--text); font-size: 32rpx; font-weight: 800; }
.rate-card, .withdraw-preview { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; padding: 18rpx; color: var(--text-sub); background: var(--bg-2); border-radius: 16rpx; }
.input-wrap { min-height: 88rpx; margin-top: 20rpx; padding: 0 20rpx; display: flex; align-items: center; gap: 16rpx; color: var(--text); border: 1rpx solid var(--border); border-radius: 16rpx; }
.input-wrap input { flex: 1; color: var(--text); }
.quick-amounts, .payment-methods, .sheet-actions { display: flex; gap: 14rpx; margin-top: 18rpx; }
.quick-amount, .payment-method { flex: 1; min-height: 64rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); background: var(--card); border: 1rpx solid var(--border); border-radius: 14rpx; }
.payment-method.active { color: var(--primary); border-color: var(--primary); }
.unavailable { display: block; margin-top: 16rpx; color: var(--down); font-size: 22rpx; }
.empty-card { display: flex; flex-direction: column; gap: 22rpx; color: var(--text-sub); }
.picker-value { min-height: 78rpx; margin: 18rpx 0; padding: 0 20rpx; display: flex; align-items: center; color: var(--text); border: 1rpx solid var(--border); border-radius: 16rpx; }
</style>
