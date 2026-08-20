<template>
  <view class="page">
    <AppNavBar :title="t('financeWithdrawalDetail')" />
    <scroll-view scroll-y class="body">
      <view v-if="loading" class="state">{{ t('loading') }}</view>
      <view v-else-if="loadError || !order" class="state error-state"><text>{{ t('withdrawalDetailLoadFailed') }}</text><view class="retry" @tap="load">{{ t('retry') }}</view></view>
      <template v-else>
        <view class="status-card" :class="statusTone(order.status)">
          <view><text class="status-title">{{ t(statusLabel(order.status)) }}</text><text class="status-sub">{{ order.order_no }}</text></view>
          <text class="status-amount">¥{{ formatMoney(order.net_amount_cny) }}</text>
        </view>

        <view class="card detail-card">
          <text class="section-title">{{ t('withdrawalInformation') }}</text>
          <view class="data-row"><text>{{ t('withdrawCardHours') }}</text><text>{{ formatNumber(order.amount_card_hours) }} {{ t('cardHour') }}</text></view>
          <view class="data-row"><text>{{ t('lockedExchangeRate') }}</text><text>¥{{ formatMoney(order.locked_rate_cny) }}</text></view>
          <view class="data-row"><text>{{ t('grossAmount') }}</text><text>¥{{ formatMoney(order.gross_amount_cny) }}</text></view>
          <view class="data-row"><text>{{ t('serviceFee') }}</text><text>¥{{ formatMoney(order.fee_cny) }}</text></view>
          <view class="data-row emphasized"><text>{{ t('netPaymentAmount') }}</text><text>¥{{ formatMoney(order.net_amount_cny) }}</text></view>
          <view class="data-row"><text>{{ t('submittedAt') }}</text><text>{{ formatDate(order.created_at || undefined) }}</text></view>
        </view>

        <view class="card detail-card">
          <view class="section-head"><text class="section-title">{{ t('bankPaymentInformation') }}</text><text v-if="order.status === 'manual_payment_pending' && !instructions" class="reveal-link" @tap="confirmReveal">{{ t('revealFullCard') }}</text></view>
          <view class="data-row"><text>{{ t('bankName') }}</text><text>{{ tr(order.bank_card.bank_name) }}</text></view>
          <view class="data-row"><text>{{ t('cardholder') }}</text><text>{{ order.bank_card.holder }}</text></view>
          <view class="data-row"><text>{{ t('bankCardNumber') }}</text><text class="mono" @tap="instructions && copyCardNumber()">{{ instructions?.card_number || order.bank_card.card_number }}</text></view>
          <view v-if="instructions?.phone" class="data-row"><text>{{ t('reservedPhone') }}</text><text>{{ instructions.phone }}</text></view>
          <text v-if="instructions" class="verification-warning">{{ t('bankCardFormatOnlyPaymentWarning') }}</text>
          <text v-if="instructions" class="audit-note">{{ t('sensitiveAccessAudited') }}</text>
        </view>

        <view v-if="order.review_note || order.failure_reason" class="card detail-card">
          <text class="section-title">{{ t('reviewInformation') }}</text>
          <text class="note-text">{{ tr(order.failure_reason || order.review_note || '') }}</text>
        </view>

        <view v-if="order.status === 'reviewing'" class="card action-card">
          <text class="section-title">{{ t('reviewWithdrawal') }}</text>
          <text class="action-hint">{{ t('approveWithdrawalFreezeHint') }}</text>
          <textarea class="note-input" v-model="reviewNote" :placeholder="t('reviewNoteOptional')" placeholder-class="placeholder" maxlength="200" />
          <view class="action-row"><view class="button danger-outline" @tap="openReason('reject')">{{ t('rejectAndUnfreeze') }}</view><view class="button primary" :class="{ disabled: submitting }" @tap="approveOrder">{{ t('approveForManualPayment') }}</view></view>
        </view>

        <view v-else-if="order.status === 'manual_payment_pending'" class="card action-card">
          <text class="section-title">{{ t('manualPaymentReceipt') }}</text>
          <text class="action-hint">{{ t('markPaidRequiresReceipt') }}</text>
          <view class="payee-confirm-row" :class="{ disabled: !instructions }" @tap="togglePayeeConfirmation">
            <view class="check-box" :class="{ checked: payeeConfirmed }">{{ payeeConfirmed ? '✓' : '' }}</view>
            <text>{{ t('confirmPayeeBeforeTransfer') }}</text>
          </view>
          <text class="verification-warning">{{ t('bankCardFormatOnlyPaymentWarning') }}</text>
          <view class="field"><text class="field-label">{{ t('bankReference') }}</text><input class="field-input" v-model="paidForm.bank_reference" :placeholder="t('enterBankReference')" placeholder-class="placeholder" /></view>
          <view class="field"><text class="field-label">{{ t('actualPaidAmount') }}</text><input class="field-input" v-model="paidForm.paid_amount_cny" type="digit" :placeholder="formatMoney(order.net_amount_cny)" placeholder-class="placeholder" /></view>
          <view class="field"><text class="field-label">{{ t('paymentTime') }}</text><input class="field-input" v-model="paidForm.paid_at" :placeholder="t('isoTimePlaceholder')" placeholder-class="placeholder" /></view>
          <view class="receipt-picker" :class="{ selected: receiptPath }" @tap="chooseReceipt"><text class="receipt-name">{{ receiptName || t('chooseReceiptFile') }}</text><text class="receipt-hint">{{ t('receiptFormatHint') }}</text></view>
          <view class="action-row"><view class="button danger-outline" @tap="openReason('fail')">{{ t('markFailedAndUnfreeze') }}</view><view class="button primary" :class="{ disabled: submitting || !canMarkPaid }" @tap="markPaid">{{ t(submitting ? 'uploading' : 'confirmPaid') }}</view></view>
        </view>

        <view v-else-if="order.status === 'paid'" class="card detail-card success-card">
          <text class="section-title">{{ t('paymentCompleted') }}</text>
          <view class="data-row"><text>{{ t('bankReference') }}</text><text class="mono">{{ order.bank_reference || '--' }}</text></view>
          <view class="data-row"><text>{{ t('paidAt') }}</text><text>{{ formatDate(order.paid_at || undefined) }}</text></view>
          <text class="audit-note">{{ t('receiptStoredPrivately') }}</text>
        </view>
      </template>
    </scroll-view>

    <view v-if="reasonSheet.visible" class="mask" @tap="reasonSheet.visible = false">
      <view class="sheet" @tap.stop>
        <text class="sheet-title">{{ t(reasonSheet.action === 'reject' ? 'rejectWithdrawal' : 'markWithdrawalFailed') }}</text>
        <textarea class="reason-input" v-model="reasonSheet.reason" :placeholder="t('reasonRequiredForUnfreeze')" placeholder-class="placeholder" maxlength="200" />
        <view class="action-row"><view class="button secondary" @tap="reasonSheet.visible = false">{{ t('cancel') }}</view><view class="button danger" :class="{ disabled: submitting }" @tap="submitReasonAction">{{ t('confirmAndUnfreeze') }}</view></view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { approveFinanceWithdrawal, getFinanceWithdrawal, getPaymentInstructions, markFinanceWithdrawalFailed, markFinanceWithdrawalPaid, rejectFinanceWithdrawal, type PaymentInstructions } from '@/api/finance'
import type { WithdrawalOrder, WithdrawalStatus } from '@/api/withdrawal'
import AppNavBar from '@/components/AppNavBar.vue'
import { useI18nStore } from '@/store/i18n'
import { formatDate, formatMoney, formatNumber } from '@/utils/format'

const { t, tr } = useI18nStore()
const id = ref('')
const order = ref<WithdrawalOrder | null>(null)
const instructions = ref<PaymentInstructions | null>(null)
const loading = ref(true)
const loadError = ref(false)
const submitting = ref(false)
const reviewNote = ref('')
const receiptPath = ref('')
const receiptName = ref('')
const payeeConfirmed = ref(false)
const paidForm = reactive({ bank_reference: '', paid_amount_cny: '', paid_at: '' })
const reasonSheet = reactive<{ visible: boolean; action: 'reject' | 'fail'; reason: string }>({ visible: false, action: 'reject', reason: '' })
const canMarkPaid = computed(() => Boolean(instructions.value && payeeConfirmed.value && receiptPath.value && paidForm.bank_reference.trim() && Number(paidForm.paid_amount_cny) > 0 && paidForm.paid_at.trim()))

function statusLabel(status: WithdrawalStatus) { return ({ reviewing: 'statusReviewing', manual_payment_pending: 'statusManualPaymentPending', paid: 'statusPaid', rejected: 'statusRejected', failed: 'statusFailed', canceled: 'statusCanceled' })[status] }
function statusTone(status: WithdrawalStatus) { return status === 'paid' ? 'success' : ['rejected','failed','canceled'].includes(status) ? 'danger' : status === 'manual_payment_pending' ? 'pending' : 'reviewing' }
function nowIso() {
  const date = new Date(); const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 19)
}
async function load() {
  if (!id.value) return
  loading.value = true; loadError.value = false
  try {
    order.value = await getFinanceWithdrawal(id.value)
    if (order.value.status !== 'manual_payment_pending') {
      instructions.value = null
      payeeConfirmed.value = false
    }
    if (order.value.status === 'manual_payment_pending') {
      paidForm.paid_amount_cny = Number(order.value.net_amount_cny).toFixed(2)
      if (!paidForm.paid_at) paidForm.paid_at = nowIso()
    }
  } catch { loadError.value = true }
  finally { loading.value = false }
}
function confirmReveal() {
  uni.showModal({ title: t('revealSensitiveBankData'), content: t('revealBankDataAuditConfirm'), success: async result => {
    if (!result.confirm || !order.value) return
    try { instructions.value = await getPaymentInstructions(order.value.id) } catch {}
  } })
}
function copyCardNumber() {
  if (!instructions.value?.card_number) return
  uni.setClipboardData({ data: instructions.value.card_number, success: () => uni.showToast({ title: t('copied'), icon: 'none' }) })
}
function togglePayeeConfirmation() {
  if (!instructions.value) {
    uni.showToast({ title: t('revealBankDataFirst'), icon: 'none' })
    return
  }
  payeeConfirmed.value = !payeeConfirmed.value
}
function approveOrder() {
  if (!order.value || submitting.value) return
  uni.showModal({ title: t('approveWithdrawal'), content: t('approveWithdrawalConfirm'), success: async result => {
    if (!result.confirm || !order.value) return
    submitting.value = true
    try { order.value = await approveFinanceWithdrawal(order.value.id, reviewNote.value.trim()); uni.showToast({ title: t('movedToManualPayment'), icon: 'success' }); await load() }
    finally { submitting.value = false }
  } })
}
function openReason(action: 'reject' | 'fail') { reasonSheet.visible = true; reasonSheet.action = action; reasonSheet.reason = '' }
async function submitReasonAction() {
  if (!order.value || submitting.value) return
  const reason = reasonSheet.reason.trim()
  if (!reason) return uni.showToast({ title: t('reasonRequiredForUnfreeze'), icon: 'none' })
  submitting.value = true
  try {
    order.value = reasonSheet.action === 'reject' ? await rejectFinanceWithdrawal(order.value.id, reason) : await markFinanceWithdrawalFailed(order.value.id, reason)
    reasonSheet.visible = false
    uni.showToast({ title: t('withdrawalClosedAndUnfrozen'), icon: 'success' })
    await load()
  } finally { submitting.value = false }
}
function chooseReceipt() {
  const chooseFile = (uni as any).chooseFile
  if (typeof chooseFile === 'function') {
    chooseFile({ count: 1, extension: ['jpg', 'jpeg', 'png', 'pdf'], success: (result: any) => {
      const file = result.tempFiles?.[0]
      if (!file) return
      receiptPath.value = file.path || file.tempFilePath || ''
      receiptName.value = file.name || receiptPath.value.split('/').pop() || t('receiptSelected')
    } })
    return
  }
  uni.chooseImage({ count: 1, sourceType: ['album', 'camera'], success: result => {
    receiptPath.value = result.tempFilePaths[0] || ''
    receiptName.value = receiptPath.value.split('/').pop() || t('receiptSelected')
  } })
}
async function markPaid() {
  if (!order.value || !canMarkPaid.value || submitting.value) return
  const paidAmount = Number(paidForm.paid_amount_cny)
  if (Math.abs(paidAmount - Number(order.value.net_amount_cny)) > 0.01) return uni.showToast({ title: t('paidAmountMismatch'), icon: 'none' })
  submitting.value = true
  try {
    order.value = await markFinanceWithdrawalPaid(order.value.id, receiptPath.value, {
      ...paidForm,
      payee_confirmed: 'true',
      reveal_token: instructions.value!.reveal_token,
    })
    receiptPath.value = ''; receiptName.value = ''
    payeeConfirmed.value = false
    uni.showToast({ title: t('manualPaymentConfirmed'), icon: 'success' })
    await load()
  } finally { submitting.value = false }
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
.status-card { display: flex; justify-content: space-between; align-items: center; gap: 24rpx; padding: 30rpx; margin-bottom: 18rpx; }
.status-card.reviewing { background: var(--primary-soft); border-color: rgba(24,175,196,.2); }
.status-card.pending { background: rgba(245,158,11,.08); border-color: rgba(245,158,11,.2); }
.status-card.success { background: var(--up-soft); border-color: rgba(15,157,88,.2); }
.status-card.danger { background: var(--down-soft); border-color: rgba(220,73,73,.2); }
.status-title { display: block; color: var(--text); font-size: 32rpx; font-weight: 800; }
.status-sub { display: block; color: var(--text-sub); font-size: 19rpx; margin-top: 7rpx; }
.status-amount { flex: none; color: var(--text); font-size: 36rpx; font-weight: 850; }
.detail-card, .action-card { padding: 28rpx; margin-bottom: 18rpx; }
.section-head { display: flex; align-items: center; justify-content: space-between; gap: 18rpx; }
.section-title { display: block; color: var(--text); font-size: 27rpx; font-weight: 750; margin-bottom: 14rpx; }
.section-head .section-title { margin-bottom: 0; }
.reveal-link { color: var(--primary); font-size: 22rpx; font-weight: 700; padding: 10rpx 0; }
.data-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 24rpx; color: var(--text-sub); font-size: 22rpx; padding: 13rpx 0; border-top: 1rpx solid var(--divider); }
.data-row text:last-child { color: var(--text); text-align: right; word-break: break-all; }
.data-row.emphasized text:last-child { color: var(--primary); font-size: 27rpx; font-weight: 800; }
.mono { font-variant-numeric: tabular-nums; }
.audit-note, .action-hint { display: block; color: var(--text-sub); background: var(--bg-2); border-radius: 12rpx; padding: 14rpx 16rpx; margin-top: 14rpx; font-size: 20rpx; line-height: 1.5; }
.verification-warning { display: block; color: var(--down); background: var(--down-soft); border-radius: 12rpx; padding: 14rpx 16rpx; margin-top: 14rpx; font-size: 20rpx; line-height: 1.5; }
.payee-confirm-row { display: flex; align-items: flex-start; gap: 14rpx; padding: 18rpx 0 4rpx; color: var(--text); font-size: 22rpx; line-height: 1.5; }
.payee-confirm-row.disabled { opacity: .45; }
.check-box { flex: none; width: 34rpx; height: 34rpx; display: flex; align-items: center; justify-content: center; color: #fff; border: 1rpx solid var(--border); border-radius: 8rpx; font-size: 21rpx; }
.check-box.checked { background: var(--primary); border-color: var(--primary); }
.note-text { display: block; color: var(--text-sub); font-size: 22rpx; line-height: 1.55; }
.note-input, .reason-input { width: 100%; min-height: 150rpx; padding: 18rpx; margin-top: 16rpx; color: var(--text); background: var(--input-bg); border-radius: 14rpx; font-size: 23rpx; box-sizing: border-box; }
.field { margin-top: 18rpx; }
.field-label { display: block; color: var(--text-sub); font-size: 22rpx; margin-bottom: 9rpx; }
.field-input { min-height: 76rpx; padding: 0 20rpx; color: var(--text); background: var(--input-bg); border-radius: 14rpx; font-size: 25rpx; box-sizing: border-box; }
.placeholder { color: var(--text-dim); }
.receipt-picker { min-height: 94rpx; display: flex; flex-direction: column; align-items: center; justify-content: center; margin-top: 20rpx; padding: 14rpx 18rpx; border: 1rpx dashed var(--primary); border-radius: 16rpx; text-align: center; }
.receipt-picker.selected { background: var(--primary-soft); }
.receipt-name { color: var(--primary); font-size: 23rpx; font-weight: 700; word-break: break-all; }
.receipt-hint { color: var(--text-dim); font-size: 19rpx; margin-top: 5rpx; }
.action-row { display: flex; gap: 14rpx; margin-top: 22rpx; }
.button { flex: 1; min-height: 80rpx; display: flex; align-items: center; justify-content: center; border-radius: 16rpx; padding: 0 10rpx; text-align: center; font-size: 23rpx; font-weight: 700; }
.button.primary { color: #fff; background: var(--primary); }
.button.secondary { color: var(--text-sub); background: var(--card); }
.button.danger { color: #fff; background: var(--down); }
.button.danger-outline { color: var(--down); border: 1rpx solid var(--down); }
.button.disabled { opacity: .4; }
.success-card { border-color: rgba(15,157,88,.22); }
.mask { position: fixed; inset: 0; z-index: 300; display: flex; align-items: flex-end; background: rgba(0,0,0,.42); }
.sheet { width: 100%; padding: 36rpx 32rpx calc(36rpx + var(--safe-bottom)); background: var(--bg); border-radius: 30rpx 30rpx 0 0; }
.sheet-title { display: block; color: var(--text); text-align: center; font-size: 31rpx; font-weight: 750; }
.reason-input { min-height: 190rpx; }
</style>
