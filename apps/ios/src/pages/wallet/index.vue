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
        <AmountText :value="wallet?.balance ?? 0" currency="settlement" size="xl" />
        <text v-if="formatDisplayReference(wallet?.balance ?? 0)" class="balance-reference">{{ formatDisplayReference(wallet?.balance ?? 0) }}</text>
        <DirectTradeWalletActions
          v-if="commerce.directTradeEnabled"
          :wallet="wallet"
          :pending-payment="pendingPayment"
          :recharge-prefill="directRechargePrefill"
          :open-withdrawal="directWithdrawRequested"
          @payment-started="handleDirectPaymentStarted"
          @payment-returned="handleDirectPaymentReturned"
          @wallet-updated="handleDirectWalletUpdated"
        />
      </view>

      <view class="withdraw-balance-row">
        <view class="card withdraw-balance-cell">
          <text class="c-label">{{ t('withdrawableBalance') }}</text>
          <AmountText :value="wallet?.withdrawable_balance ?? 0" currency="settlement" size="md" trend="up" />
          <text v-if="formatDisplayReference(wallet?.withdrawable_balance ?? 0)" class="balance-reference">{{ formatDisplayReference(wallet?.withdrawable_balance ?? 0) }}</text>
          <text class="balance-hint">{{ t('onlySettledEarningsWithdrawable') }}</text>
        </view>
        <view class="card withdraw-balance-cell">
          <text class="c-label">{{ t('withdrawFrozen') }}</text>
          <AmountText :value="wallet?.withdraw_frozen ?? 0" currency="settlement" size="md" />
          <text v-if="formatDisplayReference(wallet?.withdraw_frozen ?? 0)" class="balance-reference">{{ formatDisplayReference(wallet?.withdraw_frozen ?? 0) }}</text>
          <text class="balance-hint">{{ t('unfrozenOnRejectOrFailure') }}</text>
        </view>
      </view>

      <view v-if="pendingPayment" class="card payment-state" :class="`state-${paymentCardState}`">
        <view class="payment-state-head">
          <view>
            <text class="payment-state-title">{{ paymentStateTitle }}</text>
            <text class="payment-state-sub">{{ formatSettlementCny(pendingPayment.amount_cny) }}</text>
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
            <text class="payment-order-value">{{ displayBusinessReference(pendingPayment.order_no) }}</text>
          </view>
          <view class="payment-order-copy" role="button" @tap="copyRechargeOrderNo(pendingPayment.order_no)">{{ t('copyOrderNumber') }}</view>
        </view>
        <text class="payment-state-detail">{{ paymentStateDetail }}</text>
        <view v-if="paymentCardState !== 'success' && (canQueryPayment || canCancelPayment)" class="payment-state-actions action-grid">
          <view
            v-if="canQueryPayment"
            class="payment-action secondary"
            :class="{ disabled: !canQueryPayment || checkingStatus || cancelingPayment }"
            :aria-disabled="!canQueryPayment || checkingStatus || cancelingPayment"
            role="button"
            @tap="manualRefreshPayment"
          >{{ checkingStatus ? t('checkingPaymentStatus') : t('queryAndConfirmPayment') }}</view>
          <view
            v-if="canCancelPayment"
            class="payment-action danger"
            :class="{ disabled: !canCancelPayment || checkingStatus || cancelingPayment }"
            :aria-disabled="!canCancelPayment || checkingStatus || cancelingPayment"
            role="button"
            @tap="requestCancelPayment"
          >{{ cancelingPayment ? t('cancelingRechargeOrder') : t('cancelRechargeOrder') }}</view>
        </view>
        <view v-if="canDismissPaymentState" class="payment-state-actions">
          <view class="payment-action primary" role="button" @tap="dismissPaymentState">{{ t('done') }}</view>
        </view>
      </view>

      <view v-if="wallet?.revenue_settlement_enabled === false" class="service-warning">
        {{ t('revenueSettlementUnavailable') }}
        <text v-if="wallet.historical_test_revenue">{{ t('historicalRevenueExcluded', { amount: formatCardHourCurrency(wallet.historical_test_revenue) }) }}</text>
      </view>
      <view v-if="wallet?.reward_service_enabled === false && wallet.historical_test_rewards" class="service-warning">
        {{ t('rewardServiceUnavailable') }}
        <text>{{ t('historicalRewardsExcluded', { amount: formatCardHourCurrency(wallet.historical_test_rewards) }) }}</text>
      </view>

      <view class="grid">
        <view class="card cell">
          <text class="c-label">{{ t('k_bf07c4a4') }}</text>
          <AmountText :value="wallet?.frozen ?? 0" currency="settlement" size="md" />
          <text v-if="formatDisplayReference(wallet?.frozen ?? 0)" class="balance-reference">{{ formatDisplayReference(wallet?.frozen ?? 0) }}</text>
        </view>
        <view class="card cell">
          <text class="c-label">{{ t('cumulativeRevenue') }}</text>
          <AmountText :value="wallet?.total_income ?? 0" currency="settlement" size="md" trend="up" />
          <text v-if="formatDisplayReference(wallet?.total_income ?? 0)" class="balance-reference">{{ formatDisplayReference(wallet?.total_income ?? 0) }}</text>
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

  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { cancelRechargePayment, getRechargePayment, getWallet, queryRechargePayment, type RechargePaymentOrder, type WalletInfo } from '@/api/wallet'
import { useAssetStore } from '@/store/asset'
import { useUserStore } from '@/store/user'
import { getToken } from '@/utils/auth'
import { createPaymentAccountStorage } from '@/utils/payment-account-storage'
import { ApiRequestError } from '@/api/request'
import { formatCardHourCurrency, formatDisplayReference, formatNumber, formatSettlementCny } from '@/utils/format'
import AppNavBar from '@/components/AppNavBar.vue'
import AmountText from '@/components/AmountText.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import AppIcon from '@/components/AppIcon.vue'
import DirectTradeWalletActions from '@/components/direct-trade/DirectTradeWalletActions.vue'
import { navigateTo as nav } from '@/utils/nav'
import { useI18nStore } from '@/store/i18n'
import { useCommerceStore } from '@/store/commerce'
import { displayBusinessReference } from '@/utils/display-reference'
import {
  formatPaymentCountdown,
  paymentRemainingMs,
  readStoredRechargeSession,
  readRechargePrefillQuery,
  rechargeCanCancel,
  rechargeCanQuery,
  rechargeClearsCurrentSession,
  rechargeUiState,
  type RechargeUiState,
  type StoredRechargeSession,
  type RechargePrefill,
} from '@/utils/recharge-payment'

const i18n = useI18nStore()
const { t } = i18n
const assetStore = useAssetStore()
const commerce = useCommerceStore()
const userStore = useUserStore()
function paymentStorage() {
  return createPaymentAccountStorage(uni, () => ({ userId: userStore.userInfo?.id, token: getToken() }))
}
let sessionStorage: ReturnType<typeof paymentStorage> | null = null
const wallet = ref<WalletInfo | null>(null)
const loading = ref(true)
const loadError = ref(false)
const pendingPayment = ref<RechargePaymentOrder | null>(null)
const paymentSession = ref<StoredRechargeSession | null>(null)
const paymentDeadlineMs = ref<number | null>(null)
const countdownRemainingMs = ref<number | null>(null)
const checkingStatus = ref(false)
const cancelingPayment = ref(false)
const directRechargePrefill = ref<RechargePrefill | null>(null)
const directWithdrawRequested = ref(false)
const PENDING_PAYMENT_KEY = 'wod-pending-recharge-order'
const PAYMENT_POLL_INTERVAL_MS = 5000
let pageActive = false
let pollTimer: ReturnType<typeof setInterval> | undefined
let countdownTimer: ReturnType<typeof setInterval> | undefined
let expiryRefreshOrderNo = ''
let paymentReturnRefreshQueued = false

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
  refund_pending: 'rechargeRefundPending',
  refund_unknown: 'rechargeRefundUnknown',
  refunded: 'rechargeRefunded',
  failed: 'rechargeFailed',
  expired: 'rechargeExpired',
  canceled: 'rechargeCanceled',
}[paymentCardState.value]))
const paymentStateBadge = computed(() => t({
  pending: 'statusPendingPayment',
  processing: 'statusProcessing',
  success: 'statusCompleted',
  refund_pending: 'rechargeRefundPending',
  refund_unknown: 'rechargeRefundUnknown',
  refunded: 'rechargeRefunded',
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
      refund_pending: 'refundPendingPaymentVerificationHint',
      refund_unknown: 'refundUnknownPaymentVerificationHint',
      refunded: 'refundedPaymentVerificationHint',
      failed: 'failedPaymentVerificationHint',
      expired: 'expiredPaymentVerificationHint',
      canceled: 'canceledPaymentVerificationHint',
    }[paymentCardState.value])
})
const paymentCountdownText = computed(() => formatPaymentCountdown(countdownRemainingMs.value))
const canQueryPayment = computed(() => Boolean(
  commerce.historyReadEnabled && pendingPayment.value && rechargeCanQuery(pendingPayment.value),
))
const canCancelPayment = computed(() => Boolean(
  commerce.historyReadEnabled && pendingPayment.value && rechargeCanCancel(pendingPayment.value),
))
const canDismissPaymentState = computed(() => (
  paymentCardState.value === 'success'
  || paymentCardState.value === 'refund_pending'
  || paymentCardState.value === 'refund_unknown'
  || paymentCardState.value === 'refunded'
))
let resumePromise: Promise<void> | null = null

watch(() => [userStore.token, userStore.userInfo?.id], (_current, previous) => {
  // Cached pages can survive a login change. Drop all account-owned UI and
  // polling state before any response from the old session can arrive.
  stopPaymentTracking()
  wallet.value = null
  pendingPayment.value = null
  paymentSession.value = null
  sessionStorage = null
  paymentDeadlineMs.value = null
  countdownRemainingMs.value = null
  expiryRefreshOrderNo = ''
  checkingStatus.value = false
  cancelingPayment.value = false
  paymentReturnRefreshQueued = false
  if (previous[1]) {
    directRechargePrefill.value = null
    directWithdrawRequested.value = false
  }
  loadError.value = false
  loading.value = true
  resumePromise = null
  if (pageActive) void resumePage()
}, { flush: 'sync' })

onLoad(query => {
  directRechargePrefill.value = readRechargePrefillQuery(query)
  directWithdrawRequested.value = String(query?.withdraw || '') === '1'
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
  const storage = paymentStorage()
  if (!storage.isCurrent()) return
  if (resumePromise) return resumePromise
  const pending = (async () => {
    hydratePaymentSession()
    await fetchWallet()
    if (!storage.isCurrent()) return
    await refreshPendingPayment(true, true)
    if (storage.isCurrent()) startPaymentTracking()
  })()
  resumePromise = pending
  try {
    await pending
  } finally {
    if (resumePromise === pending) resumePromise = null
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
  const storage = paymentStorage()
  if (!storage.isCurrent()) return
  loading.value = true
  loadError.value = false
  try {
    const result = await getWallet()
    if (storage.isCurrent()) wallet.value = result
  } catch {
    if (storage.isCurrent()) loadError.value = true
  } finally {
    if (storage.isCurrent()) loading.value = false
  }
}

function handleDirectPaymentStarted() {
  paymentSession.value = null
  hydratePaymentSession()
  void refreshPendingPayment(true, false)
}

function handleDirectPaymentReturned() {
  // The HTTPS return is only a signal to close the hosted checkout. Payment
  // success remains server-authoritative and must be confirmed by get/query.
  if (checkingStatus.value) {
    paymentReturnRefreshQueued = true
    return
  }
  void refreshPendingPayment(false, true)
}

function handleDirectWalletUpdated() {
  void Promise.allSettled([fetchWallet(), assetStore.refresh()])
}

function hydratePaymentSession() {
  if (paymentSession.value && sessionStorage?.isCurrent()) return
  sessionStorage = paymentStorage()
  if (!sessionStorage.isCurrent()) return
  const stored = readStoredRechargeSession(sessionStorage.getStorageSync(PENDING_PAYMENT_KEY))
  if (!stored) {
    sessionStorage.removeStorageSync(PENDING_PAYMENT_KEY)
    return
  }
  paymentSession.value = stored
  savePaymentSession()
}

function savePaymentSession() {
  if (!paymentSession.value) return
  sessionStorage?.setStorageSync(PENDING_PAYMENT_KEY, paymentSession.value)
}

function clearPaymentSession() {
  stopPaymentTracking()
  pendingPayment.value = null
  paymentSession.value = null
  paymentDeadlineMs.value = null
  countdownRemainingMs.value = null
  expiryRefreshOrderNo = ''
  sessionStorage?.removeStorageSync(PENDING_PAYMENT_KEY)
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
  const storage = sessionStorage
  if (!orderNo || !storage?.isCurrent() || checkingStatus.value) return
  const isCurrentPayment = () => storage.isCurrent() && paymentSession.value?.orderNo === orderNo
  checkingStatus.value = true
  try {
    let payment = await getRechargePayment(orderNo, silent)
    if (!isCurrentPayment()) return
    applyPayment(payment)
    if (clearCanceledCurrentPayment(payment)) return
    const stateBeforeQuery = paymentCardState.value
    if (queryProvider
      && commerce.historyReadEnabled
      && rechargeCanQuery(payment)
      && (stateBeforeQuery === 'pending' || stateBeforeQuery === 'processing' || stateBeforeQuery === 'expired')) {
      try {
        payment = await queryRechargePayment(orderNo, true)
      } catch {
        // A pending order is a normal provider response, not a frontend error.
      }
      if (!isCurrentPayment()) return
      applyPayment(payment)
      if (clearCanceledCurrentPayment(payment)) return
    }

    if (paymentCardState.value === 'success' && paymentSession.value && !paymentSession.value.successNotified) {
      // Persist before async refreshes so pageshow/onShow cannot duplicate the
      // success toast or balance refresh for the same idempotent credit.
      paymentSession.value.successNotified = true
      savePaymentSession()
      await Promise.allSettled([fetchWallet(), assetStore.refresh()])
      if (!isCurrentPayment()) return
      uni.showToast({ title: t('rechargeSuccess'), icon: 'success' })
    }

    if (!silent && paymentCardState.value !== 'success') {
      const message = paymentCardState.value === 'pending'
        ? 'paymentPending'
        : paymentCardState.value === 'processing'
          ? 'paymentProcessing'
          : paymentCardState.value === 'refund_pending'
            ? 'rechargeRefundPending'
            : paymentCardState.value === 'refund_unknown'
              ? 'rechargeRefundUnknown'
              : paymentCardState.value === 'refunded'
                ? 'rechargeRefunded'
          : 'paymentNotCompleted'
      uni.showToast({ title: t(message), icon: 'none' })
    }
  } catch (error) {
    if (!isCurrentPayment()) return
    // A forbidden/missing order cannot be recovered by this account. Remove
    // only its local pointer; transient network failures retain retry state.
    if (error instanceof ApiRequestError && (error.statusCode === 404 || error.statusCode === 403)) {
      clearPaymentSession()
    } else if (!silent) uni.showToast({ title: t('paymentStatusUnavailable'), icon: 'none' })
  } finally {
    if (storage.isCurrent()) {
      checkingStatus.value = false
      startPaymentTracking()
      if (paymentReturnRefreshQueued) {
        paymentReturnRefreshQueued = false
        void refreshPendingPayment(false, true)
      }
    }
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
  const storage = sessionStorage
  const orderNo = paymentSession.value.orderNo
  if (!storage?.isCurrent() || !await confirmCancelPayment() || !storage.isCurrent()) return

  cancelingPayment.value = true
  stopPaymentTracking()
  try {
    const payment = await cancelRechargePayment(orderNo, true)
    if (!storage.isCurrent()) return
    if (clearCanceledCurrentPayment(payment)) {
      uni.showToast({ title: t('rechargeOrderCanceled'), icon: 'success' })
      return
    }
    applyPayment(payment)
    uni.showToast({ title: t('rechargeCancelNotAllowed'), icon: 'none' })
  } catch {
    // Preserve both the order number and server state so the user can retry.
    if (storage.isCurrent()) uni.showToast({ title: t('rechargeCancelFailed'), icon: 'none' })
  } finally {
    if (storage.isCurrent()) {
      cancelingPayment.value = false
      startPaymentTracking()
    }
  }
}

function dismissPaymentState() {
  clearPaymentSession()
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
.payment-state.state-canceled,
.payment-state.state-refund_unknown,
.payment-state.state-refunded { border-color: rgba(220, 73, 73, 0.24); }
.payment-state-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20rpx; }
.payment-state-title { display: block; color: var(--text); font-size: 27rpx; font-weight: 700; }
.payment-state-sub { display: block; color: var(--text-sub); font-size: 23rpx; margin-top: 6rpx; }
.payment-state-badge { flex: none; padding: 8rpx 14rpx; color: var(--primary); background: var(--primary-soft); border-radius: 999rpx; font-size: 21rpx; font-weight: 700; }
.state-success .payment-state-badge { color: var(--up); background: rgba(15, 157, 88, 0.1); }
.state-failed .payment-state-badge,
.state-expired .payment-state-badge,
.state-canceled .payment-state-badge,
.state-refund_unknown .payment-state-badge,
.state-refunded .payment-state-badge { color: var(--down); background: rgba(220, 73, 73, 0.09); }
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
.balance-reference { display: block; margin-top: 7rpx; color: var(--text-sub); font-size: 21rpx; font-variant-numeric: tabular-nums; }
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
