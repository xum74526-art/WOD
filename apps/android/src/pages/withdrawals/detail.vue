<template>
  <view class="page">
    <AppNavBar :title="t('withdrawalDetail')" />
    <scroll-view scroll-y class="body">
      <view v-if="loading" class="state">{{ t('loading') }}</view>
      <view v-else-if="loadError || !order" class="state error-state"><text>{{ t('withdrawalDetailLoadFailed') }}</text><view class="retry" @tap="load">{{ t('retry') }}</view></view>
      <template v-else>
        <view class="status-card" :class="statusTone(order.status)">
          <text class="status-title">{{ t(statusLabel(order.status)) }}</text>
          <text class="status-desc">{{ t(statusDescription(order.status)) }}</text>
          <text v-if="['rejected','failed','canceled'].includes(order.status)" class="unfreeze-note">{{ t('withdrawalFundsUnfrozen') }}</text>
        </view>

        <view class="card amount-card">
          <text class="section-label">{{ t('estimatedArrival') }}</text>
          <text class="arrival-amount">¥{{ formatMoney(order.net_amount_cny) }}</text>
          <view class="data-row"><text>{{ t('withdrawCardHours') }}</text><text>{{ formatNumber(order.amount_card_hours) }} {{ t('cardHour') }}</text></view>
          <view class="data-row"><text>{{ t('lockedExchangeRate') }}</text><text>1 {{ t('cardHour') }} = ¥{{ formatMoney(order.locked_rate_cny) }}</text></view>
          <view class="data-row"><text>{{ t('grossAmount') }}</text><text>¥{{ formatMoney(order.gross_amount_cny) }}</text></view>
          <view class="data-row"><text>{{ t('serviceFee') }}</text><text>- ¥{{ formatMoney(order.fee_cny) }}</text></view>
        </view>

        <view class="card detail-card">
          <text class="section-title">{{ t('receivingBankCard') }}</text>
          <view class="data-row"><text>{{ t('bankName') }}</text><text>{{ tr(order.bank_card.bank_name) }}</text></view>
          <view class="data-row"><text>{{ t('bankCardNumber') }}</text><text>{{ order.bank_card.card_number }}</text></view>
          <view class="data-row"><text>{{ t('cardholder') }}</text><text>{{ order.bank_card.holder }}</text></view>
        </view>

        <view class="card detail-card">
          <text class="section-title">{{ t('processingTimeline') }}</text>
          <view v-for="(step, index) in timeline" :key="step.label" class="timeline-row">
            <view class="timeline-rail"><view class="timeline-dot" :class="{ done: step.done, danger: step.danger }"></view><view v-if="index < timeline.length - 1" class="timeline-line" :class="{ done: timeline[index + 1]?.done }"></view></view>
            <view class="timeline-content"><text class="timeline-label">{{ t(step.label) }}</text><text class="timeline-desc">{{ t(step.desc) }}</text></view>
          </view>
        </view>

        <view v-if="order.failure_reason || order.review_note" class="card detail-card">
          <text class="section-title">{{ t('reviewInformation') }}</text>
          <text class="note-text">{{ tr(order.failure_reason || order.review_note || '') }}</text>
        </view>

        <view class="card detail-card">
          <view class="data-row"><text>{{ t('orderNumber') }}</text><text class="mono">{{ displayBusinessReference(order.order_no) }}</text></view>
          <view class="data-row"><text>{{ t('submittedAt') }}</text><text>{{ formatDate(order.created_at || undefined) }}</text></view>
          <view v-if="order.bank_reference" class="data-row"><text>{{ t('bankReference') }}</text><text class="mono">{{ order.bank_reference }}</text></view>
          <view v-if="order.paid_at" class="data-row"><text>{{ t('paidAt') }}</text><text>{{ formatDate(order.paid_at) }}</text></view>
        </view>

        <view v-if="order.status === 'reviewing'" class="cancel-button" :class="{ disabled: canceling }" @tap="cancelOrder">{{ t(canceling ? 'submitting' : 'cancelWithdrawal') }}</view>
      </template>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { cancelWithdrawal, getWithdrawal, type WithdrawalOrder, type WithdrawalStatus } from '@/api/withdrawal'
import AppNavBar from '@/components/AppNavBar.vue'
import { useI18nStore } from '@/store/i18n'
import { formatDate, formatMoney, formatNumber } from '@/utils/format'
import { displayBusinessReference } from '@/utils/display-reference'

const { t, tr } = useI18nStore()
const id = ref('')
const order = ref<WithdrawalOrder | null>(null)
const loading = ref(true)
const loadError = ref(false)
const canceling = ref(false)

function statusLabel(status: WithdrawalStatus) { return ({ reviewing: 'statusReviewing', manual_payment_pending: 'statusManualPaymentPending', paid: 'statusPaid', rejected: 'statusRejected', failed: 'statusFailed', canceled: 'statusCanceled' })[status] }
function statusDescription(status: WithdrawalStatus) { return ({ reviewing: 'reviewingWithdrawalHint', manual_payment_pending: 'manualPaymentPendingHint', paid: 'withdrawalPaidHint', rejected: 'withdrawalRejectedHint', failed: 'withdrawalFailedHint', canceled: 'withdrawalCanceledHint' })[status] }
function statusTone(status: WithdrawalStatus) { return status === 'paid' ? 'success' : ['rejected','failed','canceled'].includes(status) ? 'danger' : status === 'manual_payment_pending' ? 'pending' : 'reviewing' }
const timeline = computed(() => {
  if (!order.value) return []
  const status = order.value.status
  const ended = ['rejected', 'failed', 'canceled'].includes(status)
  return [
    { label: 'timelineSubmitted', desc: 'timelineSubmittedDesc', done: true, danger: false },
    { label: ended ? statusLabel(status) : 'timelineReviewed', desc: ended ? 'timelineUnfrozenDesc' : 'timelineReviewedDesc', done: status !== 'reviewing', danger: ended },
    { label: 'timelineManualTransfer', desc: 'timelineManualTransferDesc', done: status === 'paid', danger: false },
    { label: 'timelineCompleted', desc: 'timelineCompletedDesc', done: status === 'paid', danger: false },
  ]
})
async function load() {
  if (!id.value) return
  loading.value = true; loadError.value = false
  try { order.value = await getWithdrawal(id.value) } catch { loadError.value = true }
  finally { loading.value = false }
}
function cancelOrder() {
  if (!order.value || canceling.value) return
  uni.showModal({ title: t('cancelWithdrawal'), content: t('cancelWithdrawalConfirm'), success: async result => {
    if (!result.confirm || !order.value) return
    canceling.value = true
    try { order.value = await cancelWithdrawal(order.value.id); uni.showToast({ title: t('withdrawalCanceledAndUnfrozen'), icon: 'success' }) }
    finally { canceling.value = false }
  } })
}
onLoad(options => { id.value = String(options?.id || '') })
onShow(() => { void load() })
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.body { flex: 1; padding: 24rpx 32rpx calc(132rpx + var(--safe-bottom)); box-sizing: border-box; }
.state { min-height: 420rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 25rpx; }
.error-state { flex-direction: column; gap: 18rpx; }
.retry { min-height: 66rpx; padding: 0 28rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: 16rpx; font-weight: 700; }
.card, .status-card { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }
.status-card { padding: 32rpx; margin-bottom: 18rpx; }
.status-card.reviewing { background: var(--primary-soft); border-color: rgba(24,175,196,.2); }
.status-card.pending { background: rgba(245,158,11,.08); border-color: rgba(245,158,11,.2); }
.status-card.success { background: var(--up-soft); border-color: rgba(15,157,88,.2); }
.status-card.danger { background: var(--down-soft); border-color: rgba(220,73,73,.2); }
.status-title { display: block; color: var(--text); font-size: 35rpx; font-weight: 800; }
.status-desc { display: block; color: var(--text-sub); font-size: 23rpx; line-height: 1.6; margin-top: 10rpx; }
.unfreeze-note { display: block; color: var(--up); font-size: 22rpx; font-weight: 700; margin-top: 12rpx; }
.amount-card, .detail-card { padding: 28rpx; margin-bottom: 18rpx; }
.section-label { display: block; color: var(--text-sub); font-size: 22rpx; }
.arrival-amount { display: block; color: var(--primary); font-size: 56rpx; font-weight: 850; margin: 5rpx 0 22rpx; font-variant-numeric: tabular-nums; }
.section-title { display: block; color: var(--text); font-size: 27rpx; font-weight: 750; margin-bottom: 14rpx; }
.data-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 24rpx; color: var(--text-sub); font-size: 22rpx; padding: 13rpx 0; border-top: 1rpx solid var(--divider); }
.data-row text:last-child { color: var(--text); text-align: right; word-break: break-all; }
.mono { font-variant-numeric: tabular-nums; font-size: 20rpx; }
.timeline-row { display: flex; gap: 18rpx; min-height: 94rpx; }
.timeline-rail { width: 24rpx; flex: none; display: flex; flex-direction: column; align-items: center; }
.timeline-dot { width: 18rpx; height: 18rpx; margin-top: 6rpx; border-radius: 50%; background: var(--bg-2); border: 2rpx solid var(--border); box-sizing: border-box; }
.timeline-dot.done { background: var(--primary); border-color: var(--primary); }
.timeline-dot.danger { background: var(--down); border-color: var(--down); }
.timeline-line { width: 2rpx; flex: 1; background: var(--divider); }
.timeline-line.done { background: var(--primary); }
.timeline-content { padding-bottom: 26rpx; }
.timeline-label { display: block; color: var(--text); font-size: 24rpx; font-weight: 700; }
.timeline-desc { display: block; color: var(--text-sub); font-size: 20rpx; line-height: 1.45; margin-top: 5rpx; }
.note-text { display: block; color: var(--text-sub); background: var(--bg-2); border-radius: 14rpx; padding: 18rpx; font-size: 22rpx; line-height: 1.55; }
.cancel-button { min-height: 88rpx; display: flex; align-items: center; justify-content: center; color: var(--down); border: 1rpx solid var(--down); border-radius: var(--radius); font-size: 27rpx; font-weight: 750; margin-top: 24rpx; }
.cancel-button.disabled { opacity: .42; }
</style>
