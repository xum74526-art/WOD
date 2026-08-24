<template>
  <view class="page">
    <AppNavBar :title="t('wallet')" />
    <scroll-view scroll-y class="body">
      <view v-if="loading && !wallet" class="load-state">{{ t('loading') }}</view>
      <view v-else-if="loadError && !wallet" class="load-state load-error">
        <text>{{ t('dataUnavailable') }}</text>
        <view class="load-retry" role="button" @tap="fetchWallet">{{ t('retry') }}</view>
      </view>
      <template v-else>
      <view class="card balance-card">
        <text class="bc-label">{{ t('k_3c67102a') }}</text>
        <AmountText :value="toCardHours(wallet?.balance ?? 0)" prefix="卡时" size="xl" />
        <view class="bc-actions">
          <view class="btn ghost" @tap="openRecharge">{{ t('recharge') }}</view>
          <view class="btn primary" :class="{ disabled: !wallet?.withdraw_service_enabled }" @tap="openWithdraw">{{ t('withdraw') }}</view>
        </view>
      </view>

      <view class="withdraw-balance-row">
        <view class="card withdraw-balance-cell">
          <text class="c-label">{{ t('withdrawableBalance') }}</text>
          <AmountText :value="wallet?.withdrawable_balance ?? 0" :prefix="t('cardHour')" size="md" trend="up" />
          <text class="balance-hint">{{ t('onlySettledEarningsWithdrawable') }}</text>
        </view>
        <view class="card withdraw-balance-cell">
          <text class="c-label">{{ t('withdrawFrozen') }}</text>
          <AmountText :value="wallet?.withdraw_frozen ?? 0" :prefix="t('cardHour')" size="md" />
          <text class="balance-hint">{{ t('unfrozenOnRejectOrFailure') }}</text>
        </view>
      </view>

      <view v-if="pendingPayment" class="card payment-state" :class="`state-${paymentCardState}`">
        <view class="payment-state-head">
          <view>
            <text class="payment-state-title">{{ paymentStateTitle }}</text>
            <text class="payment-state-sub">{{ formatMoney(pendingPayment.amount_cny) }} {{ t('cny') }} · {{ formatNumber(pendingPayment.card_hours, { maximumFractionDigits: 6 }) }} {{ t('cardHour') }}</text>
          </view>
          <text class="payment-state-badge">{{ paymentStateBadge }}</text>
        </view>
        <view v-if="paymentCardState === 'pending'" class="payment-deadline">
          <text>{{ t('paymentTimeRemaining') }}</text>
          <text class="payment-countdown">{{ paymentCountdownText }}</text>
        </view>
        <view class="payment-order-number">
          <view>
            <text class="payment-order-label">{{ t('rechargeOrderNumber') }}</text>
            <text class="payment-order-value">{{ pendingPayment.order_no }}</text>
          </view>
          <view class="payment-order-copy" role="button" @tap="copyRechargeOrderNo(pendingPayment.order_no)">{{ t('copyOrderNumber') }}</view>
        </view>
        <text class="payment-state-detail">{{ paymentStateDetail }}</text>
        <view v-if="paymentCardState !== 'success'" class="payment-state-actions action-grid">
          <view
            v-if="canContinuePayment"
            class="payment-action primary"
            :class="{ disabled: checkingStatus || cancelingPayment }"
            :aria-disabled="checkingStatus || cancelingPayment"
            role="button"
            @tap="continueCurrentPayment"
          >{{ t('continuePayment') }}</view>
          <view
            class="payment-action secondary"
            :class="{ disabled: !canQueryPayment || checkingStatus || cancelingPayment }"
            :aria-disabled="!canQueryPayment || checkingStatus || cancelingPayment"
            role="button"
            @tap="manualRefreshPayment"
          >{{ checkingStatus ? t('checkingPaymentStatus') : t('queryAndConfirmPayment') }}</view>
          <view
            v-if="canReplacePayment"
            class="payment-action danger"
            :class="{ disabled: checkingStatus || cancelingPayment }"
            :aria-disabled="checkingStatus || cancelingPayment"
            role="button"
            @tap="requestReplaceRecharge"
          >{{ t('changeRechargeAmount') }}</view>
          <view
            v-else
            class="payment-action danger"
            :class="{ disabled: !canCancelPayment || checkingStatus || cancelingPayment }"
            :aria-disabled="!canCancelPayment || checkingStatus || cancelingPayment"
            role="button"
            @tap="requestCancelPayment"
          >{{ cancelingPayment ? t('cancelingRechargeOrder') : t('cancelRechargeOrder') }}</view>
          <view
            v-if="canRestartPayment"
            class="payment-action secondary"
            :class="{ disabled: checkingStatus || cancelingPayment }"
            :aria-disabled="checkingStatus || cancelingPayment"
            role="button"
            @tap="handleRestartRecharge"
          >{{ t('restartRecharge') }}</view>
        </view>
        <view v-else class="payment-state-actions">
          <view class="payment-action primary" role="button" @tap="dismissPaymentState">{{ t('done') }}</view>
        </view>
      </view>

      <view v-if="wallet?.revenue_settlement_enabled === false" class="service-warning">
        {{ t('revenueSettlementUnavailable') }}
        <text v-if="wallet.historical_test_revenue">{{ t('historicalRevenueExcluded', { amount: fmtCH(wallet.historical_test_revenue) }) }}</text>
      </view>
      <view v-if="wallet?.reward_service_enabled === false && wallet.historical_test_rewards" class="service-warning">
        {{ t('rewardServiceUnavailable') }}
        <text>{{ t('historicalRewardsExcluded', { amount: fmtCH(wallet.historical_test_rewards) }) }}</text>
      </view>

      <view class="grid">
        <view class="card cell">
          <text class="c-label">{{ t('k_bf07c4a4') }}</text>
          <AmountText :value="toCardHours(wallet?.frozen ?? 0)" prefix="卡时" size="md" />
        </view>
        <view class="card cell">
          <text class="c-label">{{ t('cumulativeRevenue') }}</text>
          <AmountText :value="toCardHours(wallet?.total_income ?? 0)" prefix="卡时" size="md" trend="up" />
        </view>
      </view>

      <SectionHeader :title="t('k_e4738b30')" />
      <view class="card menu">
        <view class="menu-item" @tap="goRechargeOrders">
          <view class="mi-left">
            <AppIcon name="order" :size="40" />
            <text class="mi-text">{{ t('rechargeOrders') }}</text>
          </view>
          <AppIcon name="chevron" :size="36" />
        </view>
        <view class="menu-item menu-divider" @tap="goLedger">
          <view class="mi-left">
            <AppIcon name="wallet" :size="40" />
            <text class="mi-text">{{ t('k_07e455b2') }}</text>
          </view>
          <AppIcon name="chevron" :size="36" />
        </view>
        <view class="menu-item menu-divider" @tap="goWithdrawals">
          <view class="mi-left">
            <AppIcon name="bank-card" :size="40" />
            <text class="mi-text">{{ t('withdrawalRecords') }}</text>
          </view>
          <AppIcon name="chevron" :size="36" />
        </view>
      </view>
      </template>
    </scroll-view>

    <!-- 充值弹窗 -->
    <view v-if="sheet.type === 'recharge'" class="mask" @tap="closeSheet">
      <view class="sheet" @tap.stop>
        <text class="sheet-title">{{ t('k_2d1872ca') }}</text>
        <view class="rate-card">
          <text class="rate-main">1 {{ t('cardHour') }} = {{ formatNumber(cardHourRate, { minimumFractionDigits: 3, maximumFractionDigits: 3 }) }} {{ t('cny') }}</text>
          <text class="rate-sub">{{ t('rechargeRateLockedHint') }}</text>
        </view>
        <view class="input-wrap">
          <text class="cur">¥</text>
          <input class="amt-input" v-model="sheet.amount" type="digit" :placeholder="t('enterRechargeCny')" placeholder-class="ph" />
        </view>
        <view class="quick-amounts">
          <view v-for="amount in quickAmounts" :key="amount" class="quick-amount" @tap="sheet.amount = String(amount)">¥{{ amount }}</view>
        </view>
        <text class="sheet-label payment-method-label">{{ t('paymentMethod') }}</text>
        <view class="payment-methods">
          <view
            v-for="method in paymentMethods"
            :key="method.value"
            class="payment-method"
            :class="{ active: sheet.paymentType === method.value }"
            @tap="sheet.paymentType = method.value"
          >
            <text class="payment-method-mark" :class="method.value">{{ method.mark }}</text>
            <text>{{ t(method.label) }}</text>
          </view>
        </view>
        <view class="conversion-preview">
          <text>{{ t('estimatedCardHours') }}</text>
          <text class="conversion-value">{{ formatNumber(estimatedCardHours, { maximumFractionDigits: 6 }) }} {{ t('cardHour') }}</text>
        </view>
        <text class="payment-hint">{{ t('mapayCheckoutHint') }}</text>
        <text class="payment-time-limit">{{ t('rechargePaymentTimeLimit', { minutes: checkoutTtlMinutes }) }}</text>
        <text v-if="!rechargeEnabled" class="payment-unavailable">{{ t('mapayKeyPending') }}</text>
        <view class="sheet-btns">
          <view class="sheet-btn cancel" @tap="closeSheet">{{ t('cancel') }}</view>
          <view class="sheet-btn primary" :class="{ disabled: !rechargeEnabled || submitting }" @tap="onRecharge">{{ submitting ? t('submitting') : t('payAndRecharge') }}</view>
        </view>
      </view>
    </view>

    <!-- 提现弹窗 -->
    <view v-if="sheet.type === 'withdraw'" class="mask" @tap="closeSheet">
      <view class="sheet" @tap.stop>
        <text class="sheet-title">{{ t('k_1b3593c1') }}</text>
        <view v-if="!bankCards.length" class="no-card">
          <text class="no-card-text">{{ t('k_5cdf6123') }}</text>
          <view class="sheet-btn primary" @tap="goBankCards" style="margin-top: 20rpx">{{ t('k_e2f477a5') }}</view>
        </view>
        <template v-else>
          <view class="manual-transfer-note">
            <text class="manual-transfer-title">{{ t('manualTransfer') }}</text>
            <text class="manual-transfer-text">{{ t('manualWithdrawalFlowHint') }}</text>
          </view>
          <view class="withdraw-summary">
            <view><text>{{ t('withdrawableBalance') }}</text><text>{{ fmtCardHours(wallet?.withdrawable_balance ?? 0) }} {{ t('cardHour') }}</text></view>
            <view><text>{{ t('exchangeRate') }}</text><text>1 {{ t('cardHour') }} = {{ formatMoney(withdrawConfig?.rate_cny_per_card_hour || 0) }} {{ t('cny') }}</text></view>
          </view>
          <view class="input-wrap">
            <text class="cur">{{ t('cardHour') }}</text>
            <input class="amt-input" v-model="sheet.amount" type="digit" :placeholder="t('withdrawableValue', { amount: `${fmtCardHours(wallet?.withdrawable_balance ?? 0)} ${t('cardHour')}` })" placeholder-class="ph" />
          </view>
          <text class="sheet-label">{{ t('k_7d66b940') }}</text>
          <picker :range="bankCards" range-key="displayName" :value="cardIndex" @change="onCardChange" class="card-picker">
            <view class="picker-text">{{ bankCards[cardIndex]?.displayName || t('请选择银行卡') }}</view>
          </picker>
          <view class="settlement-preview">
            <view><text>{{ t('grossAmount') }}</text><text>¥{{ formatMoney(withdrawGross) }}</text></view>
            <view><text>{{ t('serviceFee') }} ({{ formatNumber((withdrawConfig?.fee_rate || 0) * 100, { maximumFractionDigits: 2 }) }}%)</text><text>- ¥{{ formatMoney(withdrawFee) }}</text></view>
            <view class="net-row"><text>{{ t('estimatedArrival') }}</text><text>¥{{ formatMoney(withdrawNet) }}</text></view>
          </view>
          <view class="sheet-btns">
            <view class="sheet-btn cancel" @tap="closeSheet">{{ t('cancel') }}</view>
            <view class="sheet-btn primary" :class="{ disabled: submitting }" @tap="onWithdraw">{{ t(submitting ? 'submitting' : 'submitWithdrawalRequest') }}</view>
          </view>
        </template>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, reactive } from 'vue'
import { onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { cancelRechargePayment, createRechargePayment, getRechargePayment, getWallet, queryRechargePayment, type RechargePaymentOrder, type RechargePaymentType, type WalletInfo } from '@/api/wallet'
import { getBankCards, type BankCardItem } from '@/api/bank-card'
import { createWithdrawal, getWithdrawalConfig, type WithdrawalConfig } from '@/api/withdrawal'
import { isRegisteredBankCardStatus } from '@/utils/bank-card'
import { useAssetStore } from '@/store/asset'
import { fmtCardHours, fmtCH, fmtCHr, formatMoney, formatNumber, toCardHours } from '@/utils/format'
import { resolveBackendUrl } from '@/utils/config'
import AppNavBar from '@/components/AppNavBar.vue'
import AmountText from '@/components/AmountText.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import AppIcon from '@/components/AppIcon.vue'
import { navigateTo as nav } from '@/utils/nav'
import { useI18nStore } from '@/store/i18n'
import { openPaymentCheckout, type PaymentCheckoutFailure } from '@/utils/payment-checkout'
import {
  DEFAULT_RECHARGE_TTL_SECONDS,
  formatPaymentCountdown,
  paymentRemainingMs,
  readRechargePrefillQuery,
  readStoredRechargeSession,
  rechargeCanCancel,
  rechargeCanQuery,
  rechargeCanRestart,
  rechargeClearsCurrentSession,
  rechargeUiState,
  type RechargePrefill,
  type RechargeUiState,
  type StoredRechargeSession,
} from '@/utils/recharge-payment'

const i18n = useI18nStore()
const { t } = i18n
const assetStore = useAssetStore()
const wallet = ref<WalletInfo | null>(null)
const withdrawConfig = ref<WithdrawalConfig | null>(null)
const bankCards = ref<(BankCardItem & { displayName: string })[]>([])
const cardIndex = ref(0)
const submitting = ref(false)
const loading = ref(true)
const loadError = ref(false)
const pendingPayment = ref<RechargePaymentOrder | null>(null)
const paymentSession = ref<StoredRechargeSession | null>(null)
const paymentDeadlineMs = ref<number | null>(null)
const countdownRemainingMs = ref<number | null>(null)
const checkingStatus = ref(false)
const cancelingPayment = ref(false)
const queuedRechargePrefill = ref<RechargePrefill | null>(null)
const PENDING_PAYMENT_KEY = 'wod-pending-recharge-order'
const PAYMENT_POLL_INTERVAL_MS = 5000
let pageActive = false
let pollTimer: ReturnType<typeof setInterval> | undefined
let countdownTimer: ReturnType<typeof setInterval> | undefined
let expiryRefreshOrderNo = ''

const sheet = reactive<{ type: '' | 'recharge' | 'withdraw'; amount: string; paymentType: RechargePaymentType }>({
  type: '',
  amount: '',
  paymentType: 'alipay',
})

const allPaymentMethods: Array<{ value: RechargePaymentType; label: string; mark: string }> = [
  { value: 'alipay', label: 'alipay', mark: '支' },
  { value: 'wxpay', label: 'wechatPay', mark: '微' },
]
const paymentMethods = computed(() => {
  const enabled = wallet.value?.payment_config?.payment_types || []
  return enabled
    .map(value => allPaymentMethods.find(method => method.value === value))
    .filter((method): method is (typeof allPaymentMethods)[number] => Boolean(method))
})

const cardHourRate = computed(() => Number(wallet.value?.payment_config?.card_hour_rmb_rate || 1.002))
const rechargeEnabled = computed(() => (
  wallet.value?.recharge_service_enabled === true
  && wallet.value?.payment_config?.enabled === true
  && paymentMethods.value.length > 0
))
const minimumAmount = computed(() => Number(wallet.value?.payment_config?.min_amount_cny || 0.01))
const maximumAmount = computed(() => Number(wallet.value?.payment_config?.max_amount_cny || 50000))
const checkoutTtlMinutes = computed(() => Math.max(
  1,
  Math.ceil(Number(wallet.value?.payment_config?.checkout_ttl_seconds || DEFAULT_RECHARGE_TTL_SECONDS) / 60),
))
const quickAmounts = [0.01, 10, 50, 100]
const estimatedCardHours = computed(() => {
  const amount = Number(sheet.amount)
  return Number.isFinite(amount) && amount > 0 ? amount / cardHourRate.value : 0
})
const withdrawGross = computed(() => Math.max(0, Number(sheet.amount) || 0) * Number(withdrawConfig.value?.rate_cny_per_card_hour || 0))
const withdrawFee = computed(() => withdrawGross.value * Number(withdrawConfig.value?.fee_rate || 0))
const withdrawNet = computed(() => Math.max(0, withdrawGross.value - withdrawFee.value))

const paymentCardState = computed<RechargeUiState>(() => (
  pendingPayment.value
    ? rechargeUiState(pendingPayment.value, countdownRemainingMs.value)
    : 'pending'
))
const paymentNeedsReview = computed(() => (
  pendingPayment.value?.status === 'review' || pendingPayment.value?.status === 'late_paid_review'
))
const paymentStateTitle = computed(() => paymentNeedsReview.value
  ? t('rechargeReviewing')
  : t({
  pending: 'rechargeAwaitingPayment',
  processing: 'rechargeProcessing',
  success: 'rechargeCredited',
  failed: 'rechargeFailed',
  expired: 'rechargeExpired',
  canceled: 'rechargeCanceled',
}[paymentCardState.value]))
const paymentStateBadge = computed(() => t({
  pending: 'statusPendingPayment',
  processing: 'statusProcessing',
  success: 'statusCompleted',
  failed: 'statusFailed',
  expired: 'statusExpired',
  canceled: 'statusCanceled',
}[paymentCardState.value]))
const paymentStateDetail = computed(() => {
  const reason = i18n.tr(pendingPayment.value?.failure_reason || '').trim()
  if (reason && (paymentNeedsReview.value || paymentCardState.value === 'failed' || paymentCardState.value === 'expired')) {
    return reason
  }
  return paymentNeedsReview.value
    ? t('reviewPaymentVerificationHint')
    : t({
      pending: 'pendingPaymentVerificationHint',
      processing: 'processingPaymentVerificationHint',
      success: 'successfulPaymentVerificationHint',
      failed: 'failedPaymentVerificationHint',
      expired: 'expiredPaymentVerificationHint',
      canceled: 'canceledPaymentVerificationHint',
    }[paymentCardState.value])
})
const paymentCountdownText = computed(() => formatPaymentCountdown(countdownRemainingMs.value))
const canQueryPayment = computed(() => Boolean(
  pendingPayment.value && rechargeCanQuery(pendingPayment.value),
))
const canCancelPayment = computed(() => Boolean(
  pendingPayment.value && rechargeCanCancel(pendingPayment.value),
))
const canRestartPayment = computed(() => Boolean(
  pendingPayment.value && rechargeCanRestart(pendingPayment.value, countdownRemainingMs.value),
))
const canContinuePayment = computed(() => Boolean(
  paymentCardState.value === 'pending' && paymentSession.value?.checkoutUrl,
))
const canReplacePayment = computed(() => Boolean(
  pendingPayment.value && paymentSession.value && paymentCardState.value === 'pending',
))

let resumePromise: Promise<void> | null = null

onLoad((query) => {
  queuedRechargePrefill.value = readRechargePrefillQuery(query)
})

onShow(() => {
  pageActive = true
  void resumePage()
})

onHide(() => {
  pageActive = false
  stopPaymentTracking()
})

onUnload(() => {
  pageActive = false
  stopPaymentTracking()
})

onMounted(() => {
  // uni-app page hooks cover route changes. The browser visibility event also
  // stops network polling when an H5 tab is backgrounded at the gateway.
  // #ifdef H5
  document.addEventListener('visibilitychange', handleVisibilityChange)
  window.addEventListener('pageshow', handleBrowserPageShow)
  // #endif
})

onUnmounted(() => {
  pageActive = false
  stopPaymentTracking()
  // #ifdef H5
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  window.removeEventListener('pageshow', handleBrowserPageShow)
  // #endif
})

async function resumePage() {
  if (resumePromise) return resumePromise
  resumePromise = (async () => {
    hydratePaymentSession()
    await fetchWallet()
    await refreshPendingPayment(true, true)
    applyQueuedRechargePrefill()
    startPaymentTracking()
  })()
  try {
    await resumePromise
  } finally {
    resumePromise = null
  }
}

function handleVisibilityChange() {
  if (document.hidden) {
    pageActive = false
    stopPaymentTracking()
    return
  }
  pageActive = true
  void resumePage()
}

function handleBrowserPageShow() {
  if (typeof document !== 'undefined' && document.hidden) return
  pageActive = true
  void resumePage()
}

async function fetchWallet() {
  loading.value = true
  loadError.value = false
  const [walletResult, cardsResult, configResult] = await Promise.allSettled([getWallet(), getBankCards(), getWithdrawalConfig()])
  if (walletResult.status === 'fulfilled') wallet.value = walletResult.value
  else loadError.value = true
  if (cardsResult.status === 'fulfilled') {
    bankCards.value = cardsResult.value.filter(c => isRegisteredBankCardStatus(c.status)).map(c => ({
      ...c,
      displayName: `${t(c.bank_name)} (${c.card_number})`,
    }))
  }
  if (configResult.status === 'fulfilled') withdrawConfig.value = configResult.value
  loading.value = false
}

function openRecharge() {
  showRechargeSheet()
}

function showRechargeSheet(prefill?: RechargePrefill) {
  if (pendingPayment.value && (paymentCardState.value === 'pending' || paymentCardState.value === 'processing')) {
    uni.showModal({
      title: t('activeRechargeExistsTitle'),
      content: t('activeRechargeExists'),
      cancelText: t('close'),
      confirmText: canContinuePayment.value ? t('continuePayment') : t('viewRechargeOrders'),
      success: result => {
        if (!result.confirm) return
        if (canContinuePayment.value) continueCurrentPayment()
        else goRechargeOrders()
      },
    })
    return
  }
  sheet.type = 'recharge'
  sheet.amount = prefill?.amount || ''
  sheet.paymentType = prefill?.paymentType && paymentMethods.value.some(method => method.value === prefill.paymentType)
    ? prefill.paymentType
    : paymentMethods.value[0]?.value || 'wxpay'
}

function applyQueuedRechargePrefill() {
  const prefill = queuedRechargePrefill.value
  if (!prefill) return
  // Consume once so pageshow/onShow cannot reopen the sheet after the user
  // closes it. showRechargeSheet still blocks a new order when another live
  // checkout exists, preserving the same safety rule as the main wallet CTA.
  queuedRechargePrefill.value = null
  showRechargeSheet(prefill)
}
async function openWithdraw() {
  if (!wallet.value?.withdraw_service_enabled || withdrawConfig.value?.enabled !== true) {
    uni.showToast({ title: t('manualWithdrawalUnavailable'), icon: 'none' })
    return
  }
  sheet.type = 'withdraw'
  sheet.amount = ''
  // 刷新银行卡列表
  if (!bankCards.value.length) {
    try {
      const cards = await getBankCards()
      bankCards.value = cards.filter(c => isRegisteredBankCardStatus(c.status)).map(c => ({
        ...c,
        displayName: `${t(c.bank_name)} (${c.card_number})`,
      }))
    } catch {}
  }
}
function closeSheet() {
  sheet.type = ''
}

function onCardChange(e: any) {
  cardIndex.value = e.detail.value
}

async function onRecharge() {
  const rawAmount = String(sheet.amount || '').trim()
  const amount = Number(rawAmount)
  if (!/^\d+(?:\.\d{1,2})?$/.test(rawAmount)
    || !Number.isFinite(amount)
    || amount < minimumAmount.value
    || amount > maximumAmount.value) {
    uni.showToast({
      title: t('invalidRechargeAmount', {
        min: formatMoney(minimumAmount.value),
        max: formatMoney(maximumAmount.value),
      }),
      icon: 'none',
    })
    return
  }
  if (!rechargeEnabled.value) {
    uni.showToast({ title: t('mapayKeyPending'), icon: 'none' })
    return
  }
  if (!paymentMethods.value.some(method => method.value === sheet.paymentType)) {
    uni.showToast({ title: t('paymentChannelUnavailable'), icon: 'none' })
    return
  }
  if (!await confirmRechargeAmount(amount)) return
  if (submitting.value) return
  submitting.value = true
  try {
    const payment = await createRechargePayment(amount, sheet.paymentType)
    const target = resolveBackendUrl(payment.checkout_url)
    if (!target) throw new Error('invalid checkout url')
    paymentSession.value = {
      version: 1,
      orderNo: payment.order_no,
      checkoutUrl: target,
      fallbackExpiresAtMs: Date.now() + Number(
        wallet.value?.payment_config?.checkout_ttl_seconds || DEFAULT_RECHARGE_TTL_SECONDS,
      ) * 1000,
      successNotified: false,
    }
    savePaymentSession()
    applyPayment(payment)
    closeSheet()
    openCheckout(target)
  } catch (error) {
    console.error('[wallet] failed to start recharge checkout', error)
    uni.showToast({ title: t('paymentStartFailed'), icon: 'none' })
  } finally {
    submitting.value = false
  }
}

function confirmRechargeAmount(amount: number): Promise<boolean> {
  return new Promise(resolve => {
    uni.showModal({
      title: t('confirmRechargeAmountTitle'),
      content: t('confirmRechargeAmountContent', {
        amount: formatMoney(amount),
        cardHours: formatNumber(amount / cardHourRate.value, { maximumFractionDigits: 6 }),
      }),
      cancelText: t('checkAmountAgain'),
      confirmText: t('confirmAndPay'),
      success: result => resolve(result.confirm === true),
      fail: () => resolve(false),
    })
  })
}

function handleCheckoutFailure(failure: PaymentCheckoutFailure) {
  console.error('[wallet] payment checkout navigation failed', failure)
  const paymentAppMissing = failure.code === 'payment-app-open-failed'
  uni.showModal({
    title: t(paymentAppMissing ? 'paymentAppUnavailableTitle' : 'paymentPageOpenFailedTitle'),
    content: t(paymentAppMissing ? 'paymentAppUnavailable' : 'paymentPageOpenFailed'),
    showCancel: false,
    confirmText: t('understood'),
  })
}

function openCheckout(url: string) {
  openPaymentCheckout(url, handleCheckoutFailure)
}

function continueCurrentPayment() {
  if (checkingStatus.value || cancelingPayment.value) return
  const target = paymentSession.value?.checkoutUrl || ''
  if (!target || paymentCardState.value !== 'pending') {
    uni.showToast({ title: t('paymentCheckoutUnavailable'), icon: 'none' })
    return
  }
  openCheckout(target)
}

function hydratePaymentSession() {
  if (paymentSession.value) return
  const stored = readStoredRechargeSession(uni.getStorageSync(PENDING_PAYMENT_KEY))
  if (!stored) {
    uni.removeStorageSync(PENDING_PAYMENT_KEY)
    return
  }
  paymentSession.value = stored
  savePaymentSession()
}

function savePaymentSession() {
  if (!paymentSession.value) return
  uni.setStorageSync(PENDING_PAYMENT_KEY, paymentSession.value)
}

function clearPaymentSession() {
  stopPaymentTracking()
  pendingPayment.value = null
  paymentSession.value = null
  paymentDeadlineMs.value = null
  countdownRemainingMs.value = null
  expiryRefreshOrderNo = ''
  uni.removeStorageSync(PENDING_PAYMENT_KEY)
}

function applyPayment(payment: RechargePaymentOrder) {
  pendingPayment.value = payment
  const remaining = paymentRemainingMs(
    payment,
    Date.now(),
    paymentSession.value?.fallbackExpiresAtMs ?? null,
  )
  if (remaining !== null) {
    paymentDeadlineMs.value = Date.now() + remaining
    countdownRemainingMs.value = remaining
  } else {
    paymentDeadlineMs.value = null
    countdownRemainingMs.value = null
  }
}

function clearCanceledCurrentPayment(payment: RechargePaymentOrder): boolean {
  if (!rechargeClearsCurrentSession(payment)) return false
  clearPaymentSession()
  return true
}

function tickPaymentCountdown() {
  if (paymentDeadlineMs.value === null) return
  countdownRemainingMs.value = Math.max(0, paymentDeadlineMs.value - Date.now())
  if (countdownRemainingMs.value > 0 || !pendingPayment.value) return
  const orderNo = pendingPayment.value.order_no
  if (expiryRefreshOrderNo === orderNo) {
    startPaymentTracking()
    return
  }
  expiryRefreshOrderNo = orderNo
  // One final provider check handles a payment completed immediately before
  // the deadline. The server remains the only authority that can add funds.
  void refreshPendingPayment(true, true)
}

function stopPaymentTracking() {
  if (pollTimer) clearInterval(pollTimer)
  if (countdownTimer) clearInterval(countdownTimer)
  pollTimer = undefined
  countdownTimer = undefined
}

function startPaymentTracking() {
  stopPaymentTracking()
  if (!pageActive || !pendingPayment.value) return
  const state = paymentCardState.value
  if (state === 'pending' && paymentDeadlineMs.value !== null) {
    countdownTimer = setInterval(tickPaymentCountdown, 1000)
    tickPaymentCountdown()
  }
  if (state !== 'pending' && state !== 'processing') return
  pollTimer = setInterval(() => {
    if (pageActive) void refreshPendingPayment(true, true)
  }, PAYMENT_POLL_INTERVAL_MS)
}

async function refreshPendingPayment(silent = true, queryProvider = true) {
  hydratePaymentSession()
  const orderNo = paymentSession.value?.orderNo || ''
  if (!orderNo || checkingStatus.value) return
  checkingStatus.value = true
  try {
    let payment = await getRechargePayment(orderNo, silent)
    applyPayment(payment)
    if (clearCanceledCurrentPayment(payment)) return
    const stateBeforeQuery = paymentCardState.value
    if (queryProvider
      && rechargeEnabled.value
      && payment.can_query !== false
      && (stateBeforeQuery === 'pending' || stateBeforeQuery === 'processing' || stateBeforeQuery === 'expired')) {
      try {
        payment = await queryRechargePayment(orderNo, true)
      } catch {
        // A pending order is a normal provider response, not a frontend error.
      }
      applyPayment(payment)
      if (clearCanceledCurrentPayment(payment)) return
    }

    if (paymentCardState.value === 'success' && paymentSession.value && !paymentSession.value.successNotified) {
      // Persist before async refreshes so pageshow/onShow cannot duplicate the
      // success toast or balance refresh for the same idempotent credit.
      paymentSession.value.successNotified = true
      savePaymentSession()
      await Promise.allSettled([fetchWallet(), assetStore.refresh()])
      uni.showToast({ title: t('rechargeSuccess'), icon: 'success' })
    }

    if (!silent && paymentCardState.value !== 'success') {
      const message = paymentCardState.value === 'pending'
        ? 'paymentPending'
        : paymentCardState.value === 'processing'
          ? 'paymentProcessing'
          : 'paymentNotCompleted'
      uni.showToast({ title: t(message), icon: 'none' })
    }
  } catch {
    if (!silent) uni.showToast({ title: t('paymentStatusUnavailable'), icon: 'none' })
  } finally {
    checkingStatus.value = false
    startPaymentTracking()
  }
}

function manualRefreshPayment() {
  if (checkingStatus.value || cancelingPayment.value) return
  if (!canQueryPayment.value) {
    uni.showToast({ title: t('paymentQueryUnavailable'), icon: 'none' })
    return
  }
  void refreshPendingPayment(false, true)
}

function confirmCancelPayment(): Promise<boolean> {
  return new Promise(resolve => {
    uni.showModal({
      title: t('cancelRechargeConfirmTitle'),
      content: t('cancelRechargeConfirmContent'),
      cancelText: t('keepRechargeOrder'),
      confirmText: t('confirmCancelRecharge'),
      confirmColor: '#dc4949',
      success: result => resolve(result.confirm === true),
      fail: () => resolve(false),
    })
  })
}

async function requestCancelPayment() {
  if (checkingStatus.value || cancelingPayment.value) return
  if (!pendingPayment.value || !paymentSession.value?.orderNo || !canCancelPayment.value) {
    uni.showToast({ title: t('rechargeCancelNotAllowed'), icon: 'none' })
    return
  }
  if (!await confirmCancelPayment()) return

  cancelingPayment.value = true
  stopPaymentTracking()
  try {
    const payment = await cancelRechargePayment(paymentSession.value.orderNo, true)
    if (clearCanceledCurrentPayment(payment)) {
      uni.showToast({ title: t('rechargeOrderCanceled'), icon: 'success' })
      return
    }
    applyPayment(payment)
    uni.showToast({ title: t('rechargeCancelNotAllowed'), icon: 'none' })
  } catch {
    // Preserve both the order number and server state so the user can retry.
    uni.showToast({ title: t('rechargeCancelFailed'), icon: 'none' })
  } finally {
    cancelingPayment.value = false
    startPaymentTracking()
  }
}

function confirmReplaceRecharge(): Promise<boolean> {
  return new Promise(resolve => {
    uni.showModal({
      title: t('changeRechargeAmountTitle'),
      content: t('changeRechargeAmountContent', {
        amount: formatMoney(pendingPayment.value?.amount_cny || 0),
      }),
      cancelText: t('keepRechargeOrder'),
      confirmText: t('changeRechargeAmount'),
      confirmColor: '#dc4949',
      success: result => resolve(result.confirm === true),
      fail: () => resolve(false),
    })
  })
}

async function requestReplaceRecharge() {
  if (checkingStatus.value || cancelingPayment.value || !canReplacePayment.value) return
  if (!await confirmReplaceRecharge()) return

  checkingStatus.value = true
  stopPaymentTracking()
  try {
    const orderNo = paymentSession.value?.orderNo || ''
    if (!orderNo) return
    const payment = await queryRechargePayment(orderNo, true)
    applyPayment(payment)
    if (paymentCardState.value !== 'pending') {
      uni.showToast({ title: t('rechargeStatusChanged'), icon: 'none' })
      return
    }
    // This intentionally abandons only the local checkout session. The old
    // provider order remains visible in history and must not be presented as
    // canceled while the provider can still accept payment.
    clearPaymentSession()
    openRecharge()
  } catch {
    uni.showToast({ title: t('paymentStatusUnavailable'), icon: 'none' })
  } finally {
    checkingStatus.value = false
    startPaymentTracking()
  }
}

function handleRestartRecharge() {
  if (checkingStatus.value || cancelingPayment.value) return
  if (!canRestartPayment.value) {
    uni.showToast({ title: t('cancelBeforeRestartRecharge'), icon: 'none' })
    return
  }
  clearPaymentSession()
  openRecharge()
}

function dismissPaymentState() {
  clearPaymentSession()
}

async function onWithdraw() {
  const amount = Number(sheet.amount)
  if (!Number.isFinite(amount) || amount < Number(withdrawConfig.value?.min_card_hours || 0) || amount > Number(withdrawConfig.value?.max_card_hours || Infinity)) {
    uni.showToast({ title: t('withdrawAmountRange', { min: formatNumber(withdrawConfig.value?.min_card_hours || 0), max: formatNumber(withdrawConfig.value?.max_card_hours || 0) }), icon: 'none' })
    return
  }
  if (amount > Number(wallet.value?.withdrawable_balance || 0)) {
    uni.showToast({ title: t('withdrawableBalanceInsufficient'), icon: 'none' })
    return
  }
  if (!bankCards.value.length) {
    uni.showToast({ title: t('k_5cdf6123'), icon: 'none' })
    return
  }
  if (submitting.value) return
  submitting.value = true
  try {
    const card = bankCards.value[cardIndex.value]
    const order = await createWithdrawal({
      amount_card_hours: amount,
      bank_card_id: card.id,
      client_request_id: createClientRequestId(),
    })
    closeSheet()
    await Promise.allSettled([fetchWallet(), assetStore.refresh()])
    uni.showToast({ title: t('withdrawalSubmitted'), icon: 'success' })
    nav(`/pages/withdrawals/detail?id=${order.id}`)
  } finally { submitting.value = false }
}

function createClientRequestId() {
  return `wd-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

function copyRechargeOrderNo(orderNo: string) {
  uni.setClipboardData({
    data: orderNo,
    success: () => uni.showToast({ title: t('orderNumberCopied'), icon: 'success' }),
  })
}

function goLedger() {
  nav('/pages/wallet/ledger')
}
function goRechargeOrders() { nav('/pages/wallet/recharges') }
function goBankCards() {
  closeSheet()
  nav('/pages/bank-cards/index')
}
function goWithdrawals() { nav('/pages/withdrawals/index') }
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.body { flex: 1; padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.load-state { min-height: 420rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 26rpx; }
.load-error { flex-direction: column; gap: 18rpx; }
.load-retry { min-height: 68rpx; padding: 0 28rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: var(--radius); font-weight: 700; }
.card { background: var(--card); border: 1rpx solid var(--card-border); border-radius: var(--radius); }
.service-warning { color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); padding: 24rpx; margin: 20rpx 0; font-size: 24rpx; line-height: 1.6; }
.service-warning text { display: block; margin-top: 6rpx; }
.payment-state { padding: 24rpx 28rpx; margin: -8rpx 0 24rpx; }
.payment-state.state-success { border-color: rgba(15, 157, 88, 0.28); }
.payment-state.state-failed,
.payment-state.state-expired,
.payment-state.state-canceled { border-color: rgba(220, 73, 73, 0.24); }
.payment-state-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20rpx; }
.payment-state-title { display: block; color: var(--text); font-size: 27rpx; font-weight: 700; }
.payment-state-sub { display: block; color: var(--text-sub); font-size: 23rpx; margin-top: 6rpx; }
.payment-state-badge { flex: none; padding: 8rpx 14rpx; color: var(--primary); background: var(--primary-soft); border-radius: 999rpx; font-size: 21rpx; font-weight: 700; }
.state-success .payment-state-badge { color: var(--up); background: rgba(15, 157, 88, 0.1); }
.state-failed .payment-state-badge,
.state-expired .payment-state-badge,
.state-canceled .payment-state-badge { color: var(--down); background: rgba(220, 73, 73, 0.09); }
.payment-deadline { min-height: 66rpx; margin-top: 18rpx; padding: 0 18rpx; display: flex; align-items: center; justify-content: space-between; color: var(--text-sub); background: var(--bg-2); border-radius: 14rpx; font-size: 23rpx; }
.payment-countdown { color: var(--text); font-size: 30rpx; font-weight: 800; font-variant-numeric: tabular-nums; letter-spacing: 1rpx; }
.payment-order-number { min-height: 76rpx; margin-top: 14rpx; padding: 13rpx 16rpx; display: flex; align-items: center; justify-content: space-between; gap: 18rpx; background: var(--bg-2); border-radius: 14rpx; }
.payment-order-label { display: block; color: var(--text-dim); font-size: 19rpx; }
.payment-order-value { display: block; max-width: 470rpx; margin-top: 4rpx; color: var(--text); font-size: 21rpx; font-weight: 700; font-variant-numeric: tabular-nums; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.payment-order-copy { flex: none; min-height: 52rpx; padding: 0 16rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: 12rpx; font-size: 20rpx; font-weight: 700; }
.payment-state-detail { display: block; margin-top: 14rpx; color: var(--text-sub); font-size: 22rpx; line-height: 1.55; }
.payment-state-actions { display: flex; gap: 14rpx; margin-top: 18rpx; }
.payment-action { flex: 1; min-height: 66rpx; padding: 0 16rpx; display: flex; align-items: center; justify-content: center; border-radius: 16rpx; font-size: 24rpx; font-weight: 700; text-align: center; }
.payment-action.primary { color: #fff; background: var(--primary); }
.payment-action.secondary { color: var(--primary); background: transparent; border: 1rpx solid var(--primary); }
.payment-action.danger { color: var(--down); background: transparent; border: 1rpx solid rgba(220, 73, 73, 0.62); }
.payment-action.disabled { opacity: 0.48; }
.action-grid { flex-wrap: wrap; }
.action-grid .payment-action { flex: 1 1 calc(50% - 7rpx); min-width: 0; padding: 0 10rpx; font-size: 22rpx; line-height: 1.25; }
.balance-card { padding: 40rpx 32rpx; margin: 24rpx 0; }
.bc-label { color: var(--text-sub); font-size: 26rpx; display: block; margin-bottom: 12rpx; }
.bc-actions { display: flex; gap: 16rpx; margin-top: 32rpx; }
.btn { flex: 1; text-align: center; padding: 24rpx 0; border-radius: var(--radius); font-size: 30rpx; font-weight: 600; }
.btn.primary { background: var(--primary); color: #fff; }
.btn.ghost { background: transparent; color: var(--primary); border: 1rpx solid var(--primary); }
.btn.disabled { opacity: 0.42; }
.grid { display: flex; gap: 16rpx; margin-bottom: 24rpx; }
.withdraw-balance-row { display: flex; gap: 16rpx; margin: -8rpx 0 24rpx; }
.withdraw-balance-cell { flex: 1; min-width: 0; padding: 24rpx; }
.balance-hint { display: block; color: var(--text-dim); font-size: 19rpx; line-height: 1.4; margin-top: 8rpx; }
.cell { flex: 1; padding: 28rpx; }
.c-label { color: var(--text-sub); font-size: 24rpx; display: block; margin-bottom: 8rpx; }
.menu { padding: 0; }
.menu-item { display: flex; justify-content: space-between; align-items: center; padding: 28rpx 32rpx; }
.menu-divider { border-top: 1rpx solid var(--divider); }
.mi-left { display: flex; align-items: center; gap: 16rpx; color: var(--primary); }
.mi-text { color: var(--text); font-size: 28rpx; }

/* 弹窗 */
.mask { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 200; display: flex; align-items: flex-end; }
.sheet { width: 100%; background: var(--bg); border-radius: 32rpx 32rpx 0 0; padding: 40rpx 32rpx calc(40rpx + var(--safe-bottom)); }
.sheet-title { color: var(--text); font-size: 34rpx; font-weight: 700; display: block; text-align: center; margin-bottom: 24rpx; }
.rate-card { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); padding: 22rpx 24rpx; margin-bottom: 18rpx; }
.rate-main { color: var(--text); font-size: 29rpx; font-weight: 800; display: block; }
.rate-sub { color: var(--text-sub); font-size: 23rpx; line-height: 1.5; display: block; margin-top: 6rpx; }
.sheet-label { color: var(--text-sub); font-size: 24rpx; display: block; margin-top: 20rpx; margin-bottom: 12rpx; }
.input-wrap { display: flex; align-items: baseline; gap: 8rpx; background: var(--input-bg); border-radius: var(--radius); padding: 24rpx 28rpx; }
.cur { color: var(--text-sub); font-size: 28rpx; }
.amt-input { flex: 1; color: var(--text); font-size: 36rpx; font-weight: 700; }
.ph { color: var(--text-dim); font-size: 28rpx; font-weight: 400; }
.quick-amounts { display: flex; gap: 12rpx; margin-top: 16rpx; }
.quick-amount { flex: 1; min-height: 64rpx; display: flex; align-items: center; justify-content: center; background: var(--card); border: 1rpx solid var(--border); border-radius: 16rpx; color: var(--text-sub); font-size: 24rpx; }
.payment-method-label { margin-top: 20rpx; }
.payment-methods { display: flex; gap: 14rpx; }
.payment-method { flex: 1; min-height: 76rpx; padding: 0 22rpx; display: flex; align-items: center; gap: 12rpx; color: var(--text-sub); background: var(--card); border: 1rpx solid var(--border); border-radius: 18rpx; font-size: 26rpx; }
.payment-method.active { color: var(--text); border-color: var(--primary); background: var(--primary-soft); }
.payment-method-mark { width: 38rpx; height: 38rpx; display: flex; align-items: center; justify-content: center; border-radius: 10rpx; color: #fff; font-size: 22rpx; font-weight: 800; }
.payment-method-mark.alipay { background: #1677ff; }
.payment-method-mark.wxpay { background: #07c160; }
.conversion-preview { display: flex; justify-content: space-between; align-items: center; margin-top: 20rpx; padding: 20rpx 0; color: var(--text-sub); font-size: 25rpx; border-bottom: 1rpx solid var(--border); }
.conversion-value { color: var(--primary); font-size: 30rpx; font-weight: 800; }
.payment-hint { display: block; color: var(--text-sub); font-size: 23rpx; line-height: 1.55; margin-top: 18rpx; }
.payment-time-limit { display: block; color: var(--down); font-size: 22rpx; line-height: 1.5; margin-top: 8rpx; }
.payment-unavailable { display: block; color: var(--down); font-size: 23rpx; line-height: 1.5; margin-top: 10rpx; }
.card-picker { background: var(--input-bg); border-radius: var(--radius); padding: 24rpx 28rpx; }
.picker-text { color: var(--text); font-size: 28rpx; }
.sheet-btns { display: flex; gap: 16rpx; margin-top: 32rpx; }
.sheet-btn { flex: 1; text-align: center; padding: 28rpx 0; border-radius: var(--radius); font-size: 30rpx; font-weight: 600; }
.sheet-btn.cancel { background: var(--card); color: var(--text-sub); }
.sheet-btn.primary { background: var(--primary); color: #fff; }
.sheet-btn.disabled { opacity: 0.42; }
.no-card { text-align: center; padding: 20rpx 0; }
.no-card-text { color: var(--text-sub); font-size: 26rpx; display: block; }
.manual-transfer-note { padding: 20rpx 22rpx; margin-bottom: 18rpx; background: var(--primary-soft); border: 1rpx solid rgba(24,175,196,.18); border-radius: 16rpx; }
.manual-transfer-title { display: block; color: var(--text); font-size: 25rpx; font-weight: 750; }
.manual-transfer-text { display: block; color: var(--text-sub); font-size: 21rpx; line-height: 1.55; margin-top: 6rpx; }
.withdraw-summary { margin-bottom: 18rpx; padding: 0 4rpx; }
.withdraw-summary view, .settlement-preview view { display: flex; align-items: center; justify-content: space-between; gap: 16rpx; color: var(--text-sub); font-size: 22rpx; padding: 9rpx 0; }
.withdraw-summary view text:last-child, .settlement-preview view text:last-child { color: var(--text); font-weight: 650; text-align: right; }
.settlement-preview { margin-top: 18rpx; padding: 16rpx 20rpx; background: var(--bg-2); border-radius: 16rpx; }
.settlement-preview .net-row { border-top: 1rpx solid var(--divider); margin-top: 6rpx; padding-top: 14rpx; }
.settlement-preview .net-row text:last-child { color: var(--primary); font-size: 28rpx; font-weight: 800; }
</style>
