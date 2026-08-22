<template>
  <view class="page">
    <AppNavBar :title="t('financeReviewCenter')" />
    <view v-if="accessLoading" class="state">{{ t('checkingPermissions') }}</view>
    <view v-else-if="!access?.is_finance_admin" class="state error-state">
      <text>{{ t('financeAccessDenied') }}</text>
    </view>
    <template v-else>
      <view class="security-banner">
        <text class="security-title">{{ t('manualFinanceWorkflow') }}</text>
        <text class="security-text">{{ t('financeSecurityNotice') }}</text>
      </view>
      <view class="tabs">
        <view v-for="item in tabs" :key="item.value" class="tab" :class="{ active: tab === item.value }" @tap="changeTab(item.value)">{{ t(item.label) }}</view>
      </view>
      <scroll-view scroll-y class="body">
        <view v-if="loading" class="state">{{ t('loading') }}</view>
        <view v-else-if="loadError" class="state error-state"><text>{{ t('financeQueueLoadFailed') }}</text><view class="retry" @tap="load">{{ t('retry') }}</view></view>

        <template v-else-if="tab === 'identity'">
          <view v-if="!verifications.length" class="card empty"><EmptyState :text="t('noPendingIdentityReviews')" /></view>
          <view v-for="item in verifications" :key="item.id" class="card review-card">
            <view class="review-head"><view><text class="review-title">{{ item.real_name }}</text><text class="review-sub">{{ item.username }} · UID {{ item.user_id }}</text></view><text class="badge pending">{{ t('statusReviewing') }}</text></view>
            <view class="data-row"><text>{{ t('idCardNumber') }}</text><text>{{ item.id_card_masked }}</text></view>
            <view v-if="hasOcrResult(item)" class="ocr-review">
              <view class="ocr-review-head">
                <view><text class="ocr-review-title">{{ t('ocrReviewSummaryTitle') }}</text><text class="ocr-review-caption">{{ t('ocrReviewSummaryCaption') }}</text></view>
                <text class="ocr-review-badge" :class="ocrClass(item)">{{ ocrLabel(item) }}</text>
              </view>
              <view v-if="normalizeOcrStatus(item.ocr_status) === 'processing'" class="ocr-review-loading">
                <view v-for="index in 5" :key="index"><view></view><view></view></view>
              </view>
              <view v-else class="ocr-review-rows">
                <view v-for="row in ocrRows(item)" :key="row.key" class="ocr-review-row">
                  <text>{{ t(row.label) }}</text><text :class="row.resultClass">{{ row.resultLabel }}</text>
                </view>
              </view>
              <text class="ocr-review-note">{{ t('ocrManualVerificationHint') }}</text>
            </view>
            <text v-if="!isOcrMatched(item)" class="warning-text">{{ t(hasViewedBothPhotos(item) ? 'ocrManualApprovalWarning' : 'viewBothPhotosBeforeManualApproval') }}</text>
            <view class="photo-row">
              <view class="photo-button" :class="{ disabled: !item.front_photo_uploaded }" @tap="openVerificationPhoto(item, 'front')"><text>{{ t('viewIdFront') }}</text><text v-if="hasViewedPhoto(item, 'front')" class="photo-viewed">✓ {{ t('photoViewed') }}</text></view>
              <view class="photo-button" :class="{ disabled: !item.back_photo_uploaded }" @tap="openVerificationPhoto(item, 'back')"><text>{{ t('viewIdBack') }}</text><text v-if="hasViewedPhoto(item, 'back')" class="photo-viewed">✓ {{ t('photoViewed') }}</text></view>
            </view>
            <text v-if="!item.front_photo_uploaded || !item.back_photo_uploaded" class="warning-text">{{ t('identityPhotosIncomplete') }}</text>
            <view class="review-actions"><view class="reject-button" @tap="openReject('identity', item.id)">{{ t('reject') }}</view><view class="approve-button" :class="{ disabled: !canApproveIdentity(item) }" @tap="approveIdentity(item)">{{ t(isOcrMatched(item) ? 'oneClickApproveIdentity' : 'approveAfterManualCheck') }}</view></view>
          </view>
        </template>

        <template v-else-if="tab === 'bank'">
          <view v-if="!bankCards.length" class="card empty"><EmptyState :text="t('noRegisteredBankCards')" /></view>
          <view v-for="card in bankCards" :key="card.id" class="card review-card">
            <view class="review-head"><view><text class="review-title">{{ tr(card.bank_name) }}</text><text class="review-sub">{{ card.card_number }}</text></view><text class="badge registered">{{ t('bankCardStatusRegistered') }}</text></view>
            <view class="data-row"><text>{{ t('cardholder') }}</text><text>{{ card.holder }}</text></view>
            <view class="data-row"><text>{{ t('reservedPhone') }}</text><text>{{ card.phone || '--' }}</text></view>
            <view class="manual-note">{{ t('bankRegistrationFinanceNotice') }}</view>
          </view>
        </template>

        <template v-else>
          <view v-if="!withdrawals.length" class="card empty"><EmptyState :text="t('noPendingWithdrawals')" /></view>
          <view v-for="order in withdrawals" :key="order.id" class="card withdrawal-card" @tap="openWithdrawal(order.id)">
            <view class="review-head"><view><text class="review-title">{{ formatNumber(order.amount_card_hours) }} {{ t('cardHour') }}</text><text class="review-sub">{{ order.order_no }} · {{ formatDate(order.created_at || undefined) }}</text></view><text class="badge" :class="order.status === 'reviewing' ? 'reviewing' : 'pending'">{{ t(order.status === 'reviewing' ? 'statusReviewing' : 'statusManualPaymentPending') }}</text></view>
            <view class="withdraw-amount"><text>{{ t('netPaymentAmount') }}</text><text>¥{{ formatMoney(order.net_amount_cny) }}</text></view>
            <view class="review-foot"><text>{{ tr(order.bank_card.bank_name) }} · {{ order.bank_card.card_number }}</text><text class="detail-link">{{ t('process') }} ›</text></view>
          </view>
        </template>
      </scroll-view>
    </template>

    <view v-if="rejectSheet.visible" class="mask" @tap="closeReject">
      <view class="sheet" @tap.stop>
        <text class="sheet-title">{{ t('enterRejectionReason') }}</text>
        <textarea class="reason-input" v-model="rejectSheet.reason" :placeholder="t('rejectionReasonRequired')" placeholder-class="placeholder" maxlength="200" />
        <view class="sheet-actions"><view class="sheet-button secondary" @tap="closeReject">{{ t('cancel') }}</view><view class="sheet-button danger" :class="{ disabled: submitting }" @tap="submitReject">{{ t(submitting ? 'submitting' : 'confirmReject') }}</view></view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getFinanceAccess, getFinanceBankCards, getFinanceVerifications, getFinanceWithdrawals, reviewFinanceVerification, type FinanceAccess, type FinanceVerification } from '@/api/finance'
import type { BankCardItem } from '@/api/bank-card'
import type { WithdrawalOrder } from '@/api/withdrawal'
import AppNavBar from '@/components/AppNavBar.vue'
import EmptyState from '@/components/EmptyState.vue'
import { useI18nStore } from '@/store/i18n'
import { formatDate, formatMoney, formatNumber } from '@/utils/format'
import { navigateTo as nav } from '@/utils/nav'
import { download } from '@/api/request'
import {
  OCR_SUMMARY_FIELDS,
  hasOcrResult,
  normalizeOcrStatus,
  ocrSummaryValue,
} from '@/utils/verification-ocr'

type FinanceTab = 'identity' | 'bank' | 'withdrawal'
const { t, tr } = useI18nStore()
const access = ref<FinanceAccess | null>(null)
const accessLoading = ref(true)
const tab = ref<FinanceTab>('identity')
const loading = ref(false)
const loadError = ref(false)
const submitting = ref(false)
const verifications = ref<FinanceVerification[]>([])
const bankCards = ref<BankCardItem[]>([])
const withdrawals = ref<WithdrawalOrder[]>([])
const viewedVerificationPhotos = ref<Record<number, Partial<Record<'front' | 'back', boolean>>>>({})
const rejectSheet = reactive<{ visible: boolean; type: 'identity'; id: number; reason: string }>({ visible: false, type: 'identity', id: 0, reason: '' })
const tabs: Array<{ value: FinanceTab; label: string }> = [
  { value: 'identity', label: 'identityReview' }, { value: 'bank', label: 'bankCardRegistry' }, { value: 'withdrawal', label: 'withdrawalReview' },
]

function ocrClass(item: FinanceVerification) {
  return `ocr-${normalizeOcrStatus(item.ocr_status) || 'not_started'}`
}
function ocrLabel(item: FinanceVerification) {
  return t(`ocrStatus_${normalizeOcrStatus(item.ocr_status) || 'not_started'}`)
}
function ocrRows(item: FinanceVerification) {
  return OCR_SUMMARY_FIELDS.map((field) => {
    const result = ocrSummaryValue(item.ocr_summary, field.key)
    const resultKey = result === null
      ? 'ocrMatchPending'
      : field.resultType === 'validity'
        ? result ? 'ocrValidityValid' : 'ocrValidityInvalid'
        : result ? 'ocrMatchYes' : 'ocrMatchNo'
    return {
      ...field,
      resultLabel: t(resultKey),
      resultClass: result === true ? 'matched' : result === false ? 'mismatched' : 'pending',
    }
  })
}
function isOcrMatched(item: FinanceVerification) {
  return normalizeOcrStatus(item.ocr_status) === 'matched'
}
function hasViewedPhoto(item: FinanceVerification, side: 'front' | 'back') {
  return viewedVerificationPhotos.value[item.id]?.[side] === true
}
function hasViewedBothPhotos(item: FinanceVerification) {
  return hasViewedPhoto(item, 'front') && hasViewedPhoto(item, 'back')
}
function markPhotoViewed(item: FinanceVerification, side: 'front' | 'back') {
  viewedVerificationPhotos.value = {
    ...viewedVerificationPhotos.value,
    [item.id]: { ...viewedVerificationPhotos.value[item.id], [side]: true },
  }
}
function canApproveIdentity(item: FinanceVerification) {
  if (!item.front_photo_uploaded || !item.back_photo_uploaded) return false
  return isOcrMatched(item) || hasViewedBothPhotos(item)
}

async function checkAccess() {
  accessLoading.value = true
  try { access.value = await getFinanceAccess() } catch { access.value = null }
  accessLoading.value = false
  if (access.value?.is_finance_admin) await load()
}
async function load() {
  loading.value = true; loadError.value = false
  try {
    if (tab.value === 'identity') verifications.value = (await getFinanceVerifications({ status_filter: 'pending', page_size: 50 })).items
    else if (tab.value === 'bank') bankCards.value = (await getFinanceBankCards({ status_filter: 'registered', page_size: 50 })).items
    else withdrawals.value = (await getFinanceWithdrawals({ page_size: 50 })).items.filter(item => ['reviewing', 'manual_payment_pending'].includes(item.status))
  } catch { loadError.value = true }
  finally { loading.value = false }
}
function changeTab(value: FinanceTab) { tab.value = value; void load() }
function openReject(type: 'identity', id: number) { rejectSheet.visible = true; rejectSheet.type = type; rejectSheet.id = id; rejectSheet.reason = '' }
function closeReject() { rejectSheet.visible = false }
async function submitReject() {
  const reason = rejectSheet.reason.trim()
  if (!reason) return uni.showToast({ title: t('rejectionReasonRequired'), icon: 'none' })
  if (submitting.value) return
  submitting.value = true
  try {
    await reviewFinanceVerification(rejectSheet.id, false, reason)
    closeReject(); uni.showToast({ title: t('reviewRejectedAndRecorded'), icon: 'success' }); await load()
  } finally { submitting.value = false }
}
function approveIdentity(item: FinanceVerification) {
  if (!canApproveIdentity(item) || submitting.value) return
  const requiresManualOverride = !isOcrMatched(item)
  uni.showModal({ title: t(requiresManualOverride ? 'approveAfterManualCheck' : 'approveIdentity'), content: t(requiresManualOverride ? 'approveAfterManualCheckConfirm' : 'approveIdentityConfirm'), success: async result => {
    if (!result.confirm) return
    submitting.value = true
    try { await reviewFinanceVerification(item.id, true); uni.showToast({ title: t('reviewApproved'), icon: 'success' }); await load() }
    finally { submitting.value = false }
  } })
}
async function openVerificationPhoto(item: FinanceVerification, side: 'front' | 'back') {
  if ((side === 'front' && !item.front_photo_uploaded) || (side === 'back' && !item.back_photo_uploaded)) return
  uni.showLoading({ title: t('loading') })
  try {
    const tempFilePath = await download({ url: `/finance/verifications/${item.id}/photo/${side}` })
    uni.previewImage({ urls: [tempFilePath], current: tempFilePath, success: () => markPhotoViewed(item, side) })
  } catch {
    // download() already presents the localized failure message.
  } finally {
    uni.hideLoading()
  }
}
function openWithdrawal(id: number) { nav(`/pages/finance/withdrawal-detail?id=${id}`) }
onShow(() => { void checkAccess() })
</script>

<style lang="scss" scoped>
.page { height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.state { min-height: 420rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 25rpx; }
.error-state { flex-direction: column; gap: 18rpx; }
.retry { min-height: 66rpx; padding: 0 28rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: 16rpx; font-weight: 700; }
.security-banner { flex: none; margin: 20rpx 32rpx 12rpx; padding: 22rpx 24rpx; color: var(--text-sub); background: var(--primary-soft); border: 1rpx solid rgba(24,175,196,.2); border-radius: var(--radius); }
.security-title { display: block; color: var(--text); font-size: 26rpx; font-weight: 750; }
.security-text { display: block; font-size: 21rpx; line-height: 1.55; margin-top: 6rpx; }
.tabs { flex: none; display: flex; gap: 8rpx; margin: 8rpx 32rpx 12rpx; padding: 6rpx; background: var(--bg-2); border-radius: 16rpx; }
.tab { flex: 1; min-height: 64rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); border-radius: 12rpx; font-size: 22rpx; text-align: center; }
.tab.active { color: var(--primary); background: var(--card); font-weight: 750; box-shadow: 0 2rpx 10rpx rgba(0,0,0,.04); }
.body { flex: 1; padding: 10rpx 32rpx calc(120rpx + var(--safe-bottom)); box-sizing: border-box; }
.card { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }
.empty { padding: 80rpx 0; }
.review-card, .withdrawal-card { padding: 26rpx 28rpx; margin-bottom: 16rpx; }
.review-head, .data-row, .review-foot, .withdraw-amount { display: flex; align-items: center; justify-content: space-between; gap: 18rpx; }
.review-title { display: block; color: var(--text); font-size: 29rpx; font-weight: 750; }
.review-sub { display: block; color: var(--text-dim); font-size: 20rpx; margin-top: 6rpx; }
.badge { flex: none; padding: 7rpx 14rpx; border-radius: 999rpx; font-size: 20rpx; font-weight: 700; }
.badge.pending { color: #a16207; background: rgba(245,158,11,.12); }
.badge.registered { color: var(--primary); background: var(--primary-soft); }
.badge.reviewing { color: var(--primary); background: var(--primary-soft); }
.data-row { color: var(--text-sub); font-size: 22rpx; padding: 13rpx 0; border-top: 1rpx solid var(--divider); }
.data-row:first-of-type { margin-top: 18rpx; }
.data-row text:last-child { color: var(--text); text-align: right; }
.ocr-review { margin-top: 16rpx; padding: 20rpx; background: var(--bg-2); border-radius: 14rpx; }
.ocr-review-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16rpx; }
.ocr-review-title { display: block; color: var(--text); font-size: 23rpx; font-weight: 750; }
.ocr-review-caption { display: block; max-width: 440rpx; margin-top: 6rpx; color: var(--text-dim); font-size: 18rpx; line-height: 1.45; }
.ocr-review-badge { flex: none; padding: 7rpx 12rpx; color: var(--text-sub); background: var(--card); border-radius: 10rpx; font-size: 18rpx; font-weight: 750; }
.ocr-review-badge.ocr-processing { color: var(--primary); background: var(--primary-soft); }
.ocr-review-badge.ocr-matched { color: #15803d; background: rgba(22,163,74,.1); }
.ocr-review-badge.ocr-review_required, .ocr-review-badge.ocr-error { color: #a16207; background: rgba(245,158,11,.12); }
.ocr-review-rows { margin-top: 14rpx; border-top: 1rpx solid var(--divider); }
.ocr-review-row { min-height: 56rpx; display: flex; align-items: center; justify-content: space-between; color: var(--text-sub); font-size: 20rpx; border-bottom: 1rpx solid var(--divider); }
.ocr-review-row text:last-child { font-weight: 750; }
.ocr-review-row .matched { color: #15803d; }
.ocr-review-row .mismatched { color: var(--down); }
.ocr-review-row .pending { color: var(--text-dim); }
.ocr-review-note { display: block; margin-top: 13rpx; color: var(--text-sub); font-size: 18rpx; line-height: 1.5; }
.ocr-review-loading { margin-top: 14rpx; border-top: 1rpx solid var(--divider); }
.ocr-review-loading > view { min-height: 56rpx; display: flex; align-items: center; justify-content: space-between; border-bottom: 1rpx solid var(--divider); }
.ocr-review-loading > view > view { width: 130rpx; height: 16rpx; border-radius: 5rpx; background: var(--card); }
.ocr-review-loading > view > view:last-child { width: 64rpx; }
.photo-row { display: flex; gap: 12rpx; margin-top: 14rpx; }
.photo-button { flex: 1; min-height: 68rpx; display: flex; flex-direction: column; gap: 4rpx; align-items: center; justify-content: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: 14rpx; font-size: 22rpx; }
.photo-button.disabled { opacity: .35; }
.photo-viewed { color: #15803d; font-size: 17rpx; font-weight: 650; }
.warning-text { display: block; color: var(--down); font-size: 20rpx; margin-top: 12rpx; }
.manual-note { color: var(--text-sub); background: var(--bg-2); border-radius: 12rpx; padding: 15rpx 16rpx; margin-top: 12rpx; font-size: 20rpx; line-height: 1.5; }
.review-actions { display: flex; gap: 12rpx; margin-top: 20rpx; }
.reject-button, .approve-button { flex: 1; min-height: 72rpx; display: flex; align-items: center; justify-content: center; border-radius: 15rpx; font-size: 23rpx; font-weight: 700; }
.reject-button { color: var(--down); border: 1rpx solid var(--down); }
.approve-button { color: #fff; background: var(--primary); }
.approve-button.disabled { opacity: .38; }
.withdraw-amount { padding: 20rpx 0; margin-top: 16rpx; border-top: 1rpx solid var(--divider); border-bottom: 1rpx solid var(--divider); color: var(--text-sub); font-size: 22rpx; }
.withdraw-amount text:last-child { color: var(--primary); font-size: 32rpx; font-weight: 800; }
.review-foot { color: var(--text-sub); font-size: 21rpx; padding-top: 16rpx; }
.detail-link { color: var(--primary); font-weight: 700; }
.mask { position: fixed; inset: 0; z-index: 300; display: flex; align-items: flex-end; background: rgba(0,0,0,.42); }
.sheet { width: 100%; padding: 36rpx 32rpx calc(36rpx + var(--safe-bottom)); background: var(--bg); border-radius: 30rpx 30rpx 0 0; }
.sheet-title { display: block; color: var(--text); text-align: center; font-size: 31rpx; font-weight: 750; margin-bottom: 20rpx; }
.reason-input { width: 100%; min-height: 190rpx; padding: 20rpx; color: var(--text); background: var(--input-bg); border-radius: 16rpx; font-size: 25rpx; box-sizing: border-box; }
.placeholder { color: var(--text-dim); }
.sheet-actions { display: flex; gap: 14rpx; margin-top: 24rpx; }
.sheet-button { flex: 1; min-height: 82rpx; display: flex; align-items: center; justify-content: center; border-radius: 16rpx; font-size: 26rpx; font-weight: 700; }
.sheet-button.secondary { color: var(--text-sub); background: var(--card); }
.sheet-button.danger { color: #fff; background: var(--down); }
.sheet-button.disabled { opacity: .4; }
</style>
