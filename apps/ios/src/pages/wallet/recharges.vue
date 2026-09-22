<template>
  <view class="page">
    <AppNavBar :title="t(viewMode === 'orders' ? 'rechargeOrders' : 'refundApplications')" />

    <view class="view-switch">
      <view class="view-switch-button" :class="{ active: viewMode === 'orders' }" role="button" @tap="changeView('orders')">{{ t('viewRechargeRecords') }}</view>
      <view class="view-switch-button" :class="{ active: viewMode === 'refunds' }" role="button" @tap="changeView('refunds')">{{ t('refundApplications') }}</view>
    </view>

    <view v-if="viewMode === 'orders'" class="search-panel">
      <view class="search-box">
        <AppIcon name="search" :size="34" />
        <input
          v-model="searchInput"
          class="search-input"
          :placeholder="t('searchRechargeOrderNumber')"
          placeholder-class="search-placeholder"
          confirm-type="search"
          @confirm="submitSearch"
        />
        <view v-if="searchInput" class="search-clear" role="button" @tap="clearSearch">{{ t('clearRechargeSearch') }}</view>
      </view>
      <view class="search-button" role="button" @tap="submitSearch">{{ t('searchRechargeOrders') }}</view>
    </view>

    <view v-if="viewMode === 'orders'" class="filter-scroll">
      <scroll-view scroll-x class="filter-inner" :show-scrollbar="false">
        <view class="filter-row">
          <view
            v-for="item in filters"
            :key="item.value || 'all'"
            class="filter-chip"
            :class="{ active: filter === item.value }"
            role="button"
            @tap="changeFilter(item.value)"
          >{{ t(item.label) }}</view>
        </view>
      </scroll-view>
    </view>

    <view v-else class="filter-scroll">
      <scroll-view scroll-x class="filter-inner" :show-scrollbar="false">
        <view class="filter-row">
          <view
            v-for="item in refundFilters"
            :key="item.value || 'all-refunds'"
            class="filter-chip"
            :class="{ active: refundFilter === item.value }"
            role="button"
            @tap="changeRefundFilter(item.value)"
          >{{ t(item.label) }}</view>
        </view>
      </scroll-view>
    </view>

    <scroll-view scroll-y class="body" @scrolltolower="loadMore">
      <template v-if="viewMode === 'orders'">
      <view v-if="loading && !orders.length" class="skeleton-list" :aria-label="t('loading')">
        <view v-for="index in 3" :key="index" class="skeleton-card">
          <view class="skeleton-line wide" />
          <view class="skeleton-line short" />
          <view class="skeleton-grid">
            <view class="skeleton-line" />
            <view class="skeleton-line" />
          </view>
        </view>
      </view>

      <view v-else-if="loadError && !orders.length" class="state error-state">
        <text>{{ t('rechargeHistoryLoadFailed') }}</text>
        <view class="retry" role="button" @tap="reload">{{ t('retry') }}</view>
      </view>

      <view v-else-if="!orders.length" class="empty-card">
        <EmptyState :text="t(searchOrderNo ? 'noMatchingRechargeOrders' : 'noRechargeOrders')" />
      </view>

      <view v-for="order in orders" :key="order.order_no" class="order-card">
        <view class="order-head">
          <view class="order-heading">
            <text class="order-number-label">{{ t('rechargeOrderNumber') }}</text>
            <text class="order-number">{{ displayBusinessReference(order.order_no) }}</text>
          </view>
          <text class="status" :class="statusTone(order)">{{ t(statusLabel(order)) }}</text>
        </view>

        <view class="order-number-action" role="button" @tap="copyOrderNumber(order.order_no)">
          {{ t('copyOrderNumber') }}
        </view>

        <view class="amount-row">
          <view>
            <text class="meta-label">{{ t('rechargeAmount') }}</text>
            <text class="amount-value">¥{{ formatMoney(order.amount_cny) }}</text>
          </view>
          <view class="credit-column">
            <text class="meta-label">{{ t('estimatedCardHours') }}</text>
            <text class="credit-value">{{ fmtCardHours(order.card_hours) }} {{ t('cardHour') }}</text>
          </view>
        </view>

        <view class="detail-grid">
          <view class="detail-cell">
            <text class="meta-label">{{ t('paymentMethod') }}</text>
            <text class="detail-value">{{ channelLabel(order.channel) }}</text>
          </view>
          <view class="detail-cell">
            <text class="meta-label">{{ t('rechargeCreatedAt') }}</text>
            <text class="detail-value">{{ formatOrderTime(order.created_at || undefined) }}</text>
          </view>
          <view class="detail-cell">
            <text class="meta-label">{{ order.paid_at ? t('rechargePaidAt') : t('rechargeExpiresAt') }}</text>
            <text class="detail-value">{{ formatOrderTime(order.paid_at || order.expires_at || undefined) }}</text>
          </view>
        </view>

        <text v-if="showFailureReason(order)" class="status-reason">{{ tr(order.failure_reason) }}</text>

        <view v-if="rechargeCanQuery(order) || rechargeCanCancel(order) || rechargeCanRequestRefund(order) || commerce.directTradeEnabled" class="order-actions">
          <view
            v-if="rechargeCanQuery(order)"
            class="query-button"
            :class="{ disabled: Boolean(queryingOrderNo || cancelingOrderNo) }"
            :aria-disabled="Boolean(queryingOrderNo || cancelingOrderNo)"
            role="button"
            @tap="queryOrder(order)"
          >{{ queryingOrderNo === order.order_no ? t('checkingPaymentStatus') : t('checkPaymentStatus') }}</view>
          <view
            v-if="rechargeCanCancel(order)"
            class="cancel-button"
            :class="{ disabled: Boolean(queryingOrderNo || cancelingOrderNo) }"
            :aria-disabled="Boolean(queryingOrderNo || cancelingOrderNo)"
            role="button"
            @tap="cancelOrder(order)"
          >{{ cancelingOrderNo === order.order_no ? t('cancelingRechargeOrder') : t('cancelRechargeOrder') }}</view>
          <view
            v-if="rechargeCanRequestRefund(order)"
            class="refund-button"
            role="button"
            @tap="openRefundSheet(order)"
          >{{ t('applyForRefund') }}</view>
          <DirectTradeRechargeRestartAction v-if="commerce.directTradeEnabled" :order="order" />
        </view>
      </view>

      <view v-if="loadError && orders.length" class="more-error">
        <text>{{ t('rechargeHistoryLoadFailed') }}</text>
        <view class="retry compact" role="button" @tap="loadMore">{{ t('retry') }}</view>
      </view>
      <text v-else-if="loading && orders.length" class="loading-more">{{ t('loading') }}</text>
      <text v-else-if="orders.length && !hasMore" class="loading-more">{{ t('allLoaded') }}</text>
      </template>

      <template v-else>
        <view v-if="refundLoading && !refundRequests.length" class="skeleton-list" :aria-label="t('loading')">
          <view v-for="index in 3" :key="`refund-skeleton-${index}`" class="skeleton-card">
            <view class="skeleton-line wide" />
            <view class="skeleton-line short" />
            <view class="skeleton-grid"><view class="skeleton-line" /><view class="skeleton-line" /></view>
          </view>
        </view>
        <view v-else-if="refundLoadError && !refundRequests.length" class="state error-state">
          <text>{{ t('refundRequestLoadFailed') }}</text>
          <view class="retry" role="button" @tap="reloadRefunds">{{ t('retry') }}</view>
        </view>
        <view v-else-if="!refundRequests.length" class="empty-card">
          <EmptyState :text="t('noRefundRequests')" />
        </view>
        <view v-for="request in refundRequests" :key="request.id" class="order-card refund-card">
          <view class="order-head">
            <view class="order-heading">
              <text class="order-number-label">{{ t('refundRequestNumber') }}</text>
              <text class="order-number">{{ displayBusinessReference(request.request_no) }}</text>
            </view>
            <text class="status" :class="refundPresentation(request).tone">{{ t(refundPresentation(request).labelKey) }}</text>
          </view>
          <view class="amount-row">
            <view><text class="meta-label">{{ t('refundRequestAmount') }}</text><text class="amount-value">¥{{ formatMoney(request.amount_cny) }}</text></view>
            <view class="credit-column"><text class="meta-label">{{ t('estimatedCardHours') }}</text><text class="credit-value">{{ fmtCardHours(request.card_hours) }} {{ t('cardHour') }}</text></view>
          </view>
          <view class="detail-grid">
            <view class="detail-cell"><text class="meta-label">{{ t('refundRequestOrder') }}</text><text class="detail-value business-reference">{{ displayBusinessReference(request.order_no) }}</text></view>
            <view class="detail-cell"><text class="meta-label">{{ t('refundRequestCreatedAt') }}</text><text class="detail-value">{{ formatOrderTime(request.created_at || undefined) }}</text></view>
            <view class="detail-cell"><text class="meta-label">{{ t('refundRequestUpdatedAt') }}</text><text class="detail-value">{{ formatOrderTime(request.updated_at || undefined) }}</text></view>
          </view>
          <view class="refund-reason"><text class="meta-label">{{ t('refundRequestReason') }}</text><text>{{ tr(request.reason) }}</text></view>
        </view>
        <view v-if="refundLoadError && refundRequests.length" class="more-error"><text>{{ t('refundRequestLoadFailed') }}</text><view class="retry compact" role="button" @tap="loadMoreRefunds">{{ t('retry') }}</view></view>
        <text v-else-if="refundLoading && refundRequests.length" class="loading-more">{{ t('loading') }}</text>
        <text v-else-if="refundRequests.length && !refundHasMore" class="loading-more">{{ t('allLoaded') }}</text>
      </template>
    </scroll-view>

    <view v-if="refundOrder" class="refund-mask" @tap="closeRefundSheet">
      <view class="refund-sheet" @tap.stop>
        <view class="refund-sheet-head"><view><text>{{ t('applyForRefund') }}</text><text>{{ displayBusinessReference(refundOrder.order_no) }}</text></view><view role="button" @tap="closeRefundSheet">×</view></view>
        <view class="refund-order-summary"><text>¥{{ formatMoney(refundOrder.amount_cny) }}</text><text>{{ fmtCardHours(refundOrder.card_hours) }} {{ t('cardHour') }}</text></view>
        <text class="refund-notice">{{ t('refundReviewNotice') }}</text>
        <textarea v-model="refundReason" class="refund-textarea" :placeholder="t('refundRequestReasonPlaceholder')" :maxlength="500" />
        <text class="refund-count">{{ refundReason.length }}/500</text>
        <view class="refund-sheet-actions"><view class="sheet-cancel" role="button" @tap="closeRefundSheet">{{ t('cancel') }}</view><view class="sheet-submit" :class="{ disabled: submittingRefund }" role="button" @tap="submitRefundRequest">{{ t(submittingRefund ? 'submittingRefundRequest' : 'submitRefundRequest') }}</view></view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import {
  cancelRechargePayment,
  createRechargeRefundRequest,
  getRechargeRefundRequests,
  getRechargePayments,
  queryRechargePayment,
  type RechargePaymentOrder,
  type RechargeRefundRequest,
  type RechargeRefundRequestStatus,
} from '@/api/wallet'
import AppIcon from '@/components/AppIcon.vue'
import AppNavBar from '@/components/AppNavBar.vue'
import EmptyState from '@/components/EmptyState.vue'
import DirectTradeRechargeRestartAction from '@/components/direct-trade/DirectTradeRechargeRestartAction.vue'
import { useI18nStore } from '@/store/i18n'
import { useCommerceStore } from '@/store/commerce'
import { fmtCardHours, formatMoney } from '@/utils/format'
import { rechargeCanCancel, rechargeCanQuery, rechargeCanRequestRefund, rechargeHistoryPresentation, rechargeRefundRequestPresentation } from '@/utils/recharge-payment'
import { ensureClientRequestIntent } from '@/utils/financial-request-intent'
import { displayBusinessReference } from '@/utils/display-reference'

type RechargeStatusFilter = '' | 'pending' | 'paid' | 'review' | 'refund_pending' | 'refund_unknown' | 'refunded' | 'canceled' | 'expired' | 'failed'
type RechargeView = 'orders' | 'refunds'
type RefundStatusFilter = '' | RechargeRefundRequestStatus

const { t, tr } = useI18nStore()
const commerce = useCommerceStore()
const viewMode = ref<RechargeView>('orders')
const orders = ref<RechargePaymentOrder[]>([])
const page = ref(1)
const hasMore = ref(false)
const loading = ref(false)
const loadError = ref(false)
const filter = ref<RechargeStatusFilter>('')
const searchInput = ref('')
const searchOrderNo = ref('')
const queryingOrderNo = ref('')
const cancelingOrderNo = ref('')
const refundRequests = ref<RechargeRefundRequest[]>([])
const refundPage = ref(1)
const refundHasMore = ref(false)
const refundLoading = ref(false)
const refundLoadError = ref(false)
const refundLoaded = ref(false)
const refundFilter = ref<RefundStatusFilter>('')
const refundOrder = ref<RechargePaymentOrder | null>(null)
const refundReason = ref('')
const submittingRefund = ref(false)
const REFUND_INTENT_KEY_PREFIX = 'wod-refund-request-intent'

const filters: Array<{ value: RechargeStatusFilter; label: string }> = [
  { value: '', label: 'all' },
  { value: 'pending', label: 'statusPendingPayment' },
  { value: 'paid', label: 'statusCompleted' },
  { value: 'review', label: 'statusProcessing' },
  { value: 'refund_pending', label: 'rechargeRefundPending' },
  { value: 'refund_unknown', label: 'rechargeRefundUnknown' },
  { value: 'refunded', label: 'rechargeRefunded' },
  { value: 'canceled', label: 'statusCanceled' },
  { value: 'expired', label: 'statusExpired' },
  { value: 'failed', label: 'statusFailed' },
]

const refundFilters: Array<{ value: RefundStatusFilter; label: string }> = [
  { value: '', label: 'all' },
  { value: 'pending_review', label: 'refundRequestPendingReview' },
  { value: 'approved', label: 'refundRequestApproved' },
  { value: 'processing', label: 'refundRequestProcessing' },
  { value: 'succeeded', label: 'refundRequestSucceeded' },
  { value: 'rejected', label: 'refundRequestRejected' },
  { value: 'failed', label: 'refundRequestFailed' },
  { value: 'canceled', label: 'refundRequestCanceled' },
]

function statusLabel(order: RechargePaymentOrder): string {
  return rechargeHistoryPresentation(order).labelKey
}

function statusTone(order: RechargePaymentOrder): string {
  return rechargeHistoryPresentation(order).tone
}

function refundPresentation(request: RechargeRefundRequest) {
  return rechargeRefundRequestPresentation(request)
}

function channelLabel(channel?: string | null): string {
  if (channel === 'alipay') return t('alipay')
  if (channel === 'wxpay') return t('wechatPay')
  return t('notAvailableShort')
}

function showFailureReason(order: RechargePaymentOrder): boolean {
  return Boolean(order.failure_reason && ['failed', 'review', 'late_paid_review'].includes(order.status))
}

function formatOrderTime(value?: string): string {
  if (!value) return t('notAvailableShort')
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value.replace('T', ' ').slice(0, 16)
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

async function fetchPage(reset = false) {
  if (loading.value || (!reset && !hasMore.value)) return
  loading.value = true
  loadError.value = false
  const requestedPage = reset ? 1 : page.value
  try {
    const result = await getRechargePayments({
      page: requestedPage,
      page_size: 20,
      status: filter.value || undefined,
      order_no: searchOrderNo.value || undefined,
    })
    orders.value = reset ? result.items : [...orders.value, ...result.items]
    page.value = requestedPage + 1
    hasMore.value = result.has_more
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

function reload() {
  orders.value = []
  page.value = 1
  hasMore.value = true
  void fetchPage(true)
}

async function fetchRefundPage(reset = false) {
  if (refundLoading.value || (!reset && !refundHasMore.value)) return
  refundLoading.value = true
  refundLoadError.value = false
  const requestedPage = reset ? 1 : refundPage.value
  try {
    const result = await getRechargeRefundRequests({
      page: requestedPage,
      page_size: 20,
      status: refundFilter.value || undefined,
    })
    refundRequests.value = reset ? result.items : [...refundRequests.value, ...result.items]
    refundPage.value = requestedPage + 1
    refundHasMore.value = requestedPage * result.page_size < result.total
    refundLoaded.value = true
  } catch {
    refundLoadError.value = true
  } finally {
    refundLoading.value = false
  }
}

function reloadRefunds() {
  refundRequests.value = []
  refundPage.value = 1
  refundHasMore.value = true
  void fetchRefundPage(true)
}

function loadMoreRefunds() {
  void fetchRefundPage(false)
}

function changeView(value: RechargeView) {
  viewMode.value = value
  if (value === 'refunds' && !refundLoaded.value) reloadRefunds()
}

function changeRefundFilter(value: RefundStatusFilter) {
  if (refundFilter.value === value && refundLoaded.value) return
  refundFilter.value = value
  reloadRefunds()
}

function openRefundSheet(order: RechargePaymentOrder) {
  if (!rechargeCanRequestRefund(order)) return
  refundOrder.value = order
  refundReason.value = ''
}

function closeRefundSheet() {
  if (submittingRefund.value) return
  refundOrder.value = null
  refundReason.value = ''
}

async function submitRefundRequest() {
  const order = refundOrder.value
  if (!order || submittingRefund.value) return
  const reason = refundReason.value.trim().replace(/\s+/g, ' ')
  if (reason.length < 5 || reason.length > 500) {
    uni.showToast({ title: t('refundRequestReasonInvalid'), icon: 'none' })
    return
  }
  submittingRefund.value = true
  const storageKey = `${REFUND_INTENT_KEY_PREFIX}:${order.order_no}`
  try {
    const generated = `refund-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
    const intent = ensureClientRequestIntent(
      uni.getStorageSync(storageKey),
      `${order.order_no}|${reason}`,
      generated,
    )
    uni.setStorageSync(storageKey, intent)
    await createRechargeRefundRequest(order.order_no, { client_request_id: intent.requestId, reason })
    uni.removeStorageSync(storageKey)
    refundOrder.value = null
    refundReason.value = ''
    viewMode.value = 'refunds'
    reloadRefunds()
    uni.showToast({ title: t('refundRequestSubmitted'), icon: 'none' })
  } catch {
    uni.showToast({ title: t('operationFailed'), icon: 'none' })
  } finally {
    submittingRefund.value = false
  }
}

function loadMore() {
  if (viewMode.value === 'refunds') {
    loadMoreRefunds()
    return
  }
  void fetchPage(false)
}

function changeFilter(value: RechargeStatusFilter) {
  if (filter.value === value) return
  filter.value = value
  reload()
}

function submitSearch() {
  searchOrderNo.value = searchInput.value.trim().toUpperCase()
  reload()
}

function clearSearch() {
  searchInput.value = ''
  searchOrderNo.value = ''
  reload()
}

function copyOrderNumber(orderNo: string) {
  uni.setClipboardData({
    data: orderNo,
    success: () => uni.showToast({ title: t('orderNumberCopied'), icon: 'success' }),
  })
}

async function queryOrder(order: RechargePaymentOrder) {
  if (queryingOrderNo.value || cancelingOrderNo.value || !rechargeCanQuery(order)) return
  queryingOrderNo.value = order.order_no
  try {
    const refreshed = await queryRechargePayment(order.order_no, true)
    const index = orders.value.findIndex(item => item.order_no === refreshed.order_no)
    if (index >= 0) orders.value.splice(index, 1, refreshed)
    uni.showToast({ title: t('rechargeOrderStatusUpdated'), icon: 'success' })
  } catch {
    uni.showToast({ title: t('paymentStatusUnavailable'), icon: 'none' })
  } finally {
    queryingOrderNo.value = ''
  }
}

function confirmCancelOrder(): Promise<boolean> {
  return new Promise(resolve => {
    uni.showModal({
      title: t('cancelRechargeConfirmTitle'),
      content: t('cancelRechargeConfirmContent'),
      cancelText: t('keepRechargeOrder'),
      confirmText: t('confirmCancelRecharge'),
      success: ({ confirm }) => resolve(confirm),
      fail: () => resolve(false),
    })
  })
}

async function cancelOrder(order: RechargePaymentOrder) {
  if (queryingOrderNo.value || cancelingOrderNo.value || !rechargeCanCancel(order)) return
  if (!await confirmCancelOrder()) return
  cancelingOrderNo.value = order.order_no
  try {
    const refreshed = await cancelRechargePayment(order.order_no, true)
    const index = orders.value.findIndex(item => item.order_no === refreshed.order_no)
    if (index >= 0) orders.value.splice(index, 1, refreshed)
    uni.showToast({ title: t('rechargeOrderCanceled'), icon: 'success' })
  } catch {
    uni.showToast({ title: t('rechargeCancelFailed'), icon: 'none' })
  } finally {
    cancelingOrderNo.value = ''
  }
}

onShow(() => {
  reload()
  if (refundLoaded.value) reloadRefunds()
})
</script>

<style lang="scss" scoped>
.page { width: 100%; height: 100vh; height: 100dvh; overflow: hidden; background: var(--bg); display: flex; flex-direction: column; box-sizing: border-box; }
.view-switch { width: calc(100% - 64rpx); flex: none; margin: 14rpx 32rpx 4rpx; padding: 6rpx; display: grid; grid-template-columns: 1fr 1fr; gap: 6rpx; border: 1rpx solid var(--border); border-radius: 17rpx; background: var(--bg-2); box-sizing: border-box; }
.view-switch-button { min-height: 62rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); border-radius: 12rpx; font-size: 22rpx; font-weight: 650; }
.view-switch-button.active { color: var(--primary); background: var(--card); box-shadow: 0 5rpx 14rpx rgba(10, 80, 91, .08); }
.search-panel { width: calc(100% - 64rpx); min-width: 0; flex: none; display: grid; grid-template-columns: minmax(0, 1fr) 104rpx; gap: 12rpx; margin: 0 32rpx; padding: 22rpx 0 12rpx; box-sizing: border-box; }
.search-box { min-width: 0; min-height: 72rpx; padding: 0 20rpx; display: flex; align-items: center; gap: 12rpx; color: var(--text-sub); background: var(--input-bg); border: 1rpx solid var(--border); border-radius: 16rpx; }
.search-input { width: 0; min-width: 0; flex: 1; height: 72rpx; color: var(--text); font-size: 23rpx; font-variant-numeric: tabular-nums; }
.search-placeholder { color: var(--text-dim); }
.search-clear { flex: none; min-height: 52rpx; display: flex; align-items: center; color: var(--text-sub); font-size: 21rpx; }
.search-button { width: 104rpx; min-height: 72rpx; display: flex; align-items: center; justify-content: center; color: #fff; background: var(--primary); border-radius: 16rpx; font-size: 24rpx; font-weight: 700; }
.search-button:active, .query-button:active, .cancel-button:active, .refund-button:active, .restart-button:active, .retry:active, .order-number-action:active, .sheet-cancel:active, .sheet-submit:active { transform: scale(.98); }
.filter-scroll { width: 100%; min-width: 0; flex: none; padding: 8rpx 0 12rpx; box-sizing: border-box; }
.filter-inner { width: 100%; white-space: nowrap; }
.filter-row { display: inline-flex; gap: 12rpx; padding: 0 32rpx; }
.filter-chip { min-height: 62rpx; padding: 0 23rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); background: var(--card); border: 1rpx solid var(--border); border-radius: 999rpx; font-size: 22rpx; }
.filter-chip.active { color: var(--primary); background: var(--primary-soft); border-color: var(--primary); font-weight: 700; }
.body { width: 100%; min-width: 0; flex: 1; padding: 10rpx 0 calc(80rpx + var(--safe-bottom)); overflow-x: hidden; box-sizing: border-box; }
.order-card, .empty-card, .skeleton-card { width: calc(100% - 64rpx); min-width: 0; margin: 0 32rpx 16rpx; padding: 26rpx 28rpx; background: var(--card); border: 1rpx solid var(--card-border); border-radius: var(--radius); box-sizing: border-box; }
.order-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18rpx; }
.order-heading { min-width: 0; flex: 1; }
.order-number-label, .meta-label { display: block; color: var(--text-dim); font-size: 20rpx; }
.order-number { display: block; margin-top: 5rpx; color: var(--text); font-size: 23rpx; font-weight: 750; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.status { flex: none; padding: 7rpx 14rpx; border-radius: 999rpx; font-size: 20rpx; font-weight: 700; }
.status.pending { color: #9a6100; background: rgba(245, 158, 11, .12); }
.status.reviewing { color: var(--primary); background: var(--primary-soft); }
.status.success { color: var(--up); background: var(--up-soft); }
.status.danger { color: var(--down); background: var(--down-soft); }
.order-number-action { width: fit-content; min-height: 54rpx; margin-top: 15rpx; padding: 0 17rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: 12rpx; font-size: 21rpx; font-weight: 700; }
.amount-row { min-width: 0; display: flex; align-items: flex-end; justify-content: space-between; gap: 18rpx; margin-top: 20rpx; padding: 20rpx 0; border-top: 1rpx solid var(--divider); border-bottom: 1rpx solid var(--divider); }
.amount-row > view { min-width: 0; flex: 1; }
.amount-value, .credit-value { display: block; margin-top: 7rpx; color: var(--text); font-size: 30rpx; font-weight: 800; font-variant-numeric: tabular-nums; }
.credit-column { min-width: 0; text-align: right; }
.credit-value { color: var(--primary); overflow-wrap: anywhere; }
.detail-grid { min-width: 0; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 18rpx 24rpx; padding-top: 20rpx; }
.detail-cell { min-width: 0; }
.detail-cell:last-child { grid-column: 1 / -1; }
.detail-value { display: block; margin-top: 6rpx; color: var(--text); font-size: 22rpx; line-height: 1.45; overflow-wrap: anywhere; }
.status-reason { display: block; margin-top: 18rpx; padding: 16rpx 18rpx; color: var(--text-sub); background: var(--bg-2); border-radius: 13rpx; font-size: 21rpx; line-height: 1.55; }
.order-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 12rpx; margin-top: 20rpx; }
.query-button, .cancel-button, .refund-button, .restart-button { min-height: 64rpx; padding: 0 22rpx; display: flex; align-items: center; justify-content: center; border-radius: 15rpx; font-size: 22rpx; font-weight: 700; }
.query-button { color: var(--primary); border: 1rpx solid var(--primary); }
.cancel-button { color: var(--down); border: 1rpx solid var(--down); }
.refund-button { color: var(--down); border: 1rpx solid rgba(220, 73, 73, .55); background: var(--down-soft); }
.restart-button { color: #fff; background: var(--primary); border: 1rpx solid var(--primary); }
.query-button.disabled, .cancel-button.disabled, .refund-button.disabled, .restart-button.disabled, .sheet-submit.disabled { opacity: .48; }
.business-reference { overflow-wrap: anywhere; }
.refund-reason { margin-top: 18rpx; padding: 18rpx; display: grid; gap: 8rpx; color: var(--text-sub); background: var(--bg-2); border-radius: 13rpx; font-size: 22rpx; line-height: 1.55; }
.refund-mask { position: fixed; inset: 0; z-index: 80; padding: 24rpx; padding-bottom: calc(24rpx + var(--safe-bottom)); display: flex; align-items: flex-end; background: rgba(4, 22, 27, .52); box-sizing: border-box; }
.refund-sheet { width: 100%; padding: 30rpx; border-radius: 28rpx; background: var(--card); box-shadow: 0 -16rpx 52rpx rgba(0, 0, 0, .16); box-sizing: border-box; }
.refund-sheet-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20rpx; }
.refund-sheet-head > view:first-child { min-width: 0; display: grid; gap: 8rpx; }
.refund-sheet-head > view:first-child text:first-child { color: var(--text); font-size: 30rpx; font-weight: 800; }
.refund-sheet-head > view:first-child text:last-child { color: var(--text-dim); font-size: 20rpx; overflow-wrap: anywhere; }
.refund-sheet-head > view:last-child { width: 56rpx; height: 56rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); background: var(--bg-2); border-radius: 50%; font-size: 34rpx; }
.refund-order-summary { margin-top: 22rpx; padding: 18rpx 20rpx; display: flex; justify-content: space-between; gap: 18rpx; color: var(--primary); background: var(--primary-soft); border-radius: 14rpx; font-size: 24rpx; font-weight: 750; }
.refund-notice { display: block; margin-top: 18rpx; color: var(--text-sub); font-size: 21rpx; line-height: 1.55; }
.refund-textarea { width: 100%; min-height: 180rpx; margin-top: 18rpx; padding: 20rpx; color: var(--text); background: var(--input-bg); border: 1rpx solid var(--border); border-radius: 16rpx; font-size: 24rpx; line-height: 1.5; box-sizing: border-box; }
.refund-count { display: block; margin-top: 8rpx; color: var(--text-dim); text-align: right; font-size: 20rpx; }
.refund-sheet-actions { margin-top: 20rpx; display: grid; grid-template-columns: .72fr 1.28fr; gap: 14rpx; }
.sheet-cancel, .sheet-submit { min-height: 78rpx; display: flex; align-items: center; justify-content: center; border-radius: 16rpx; font-size: 24rpx; font-weight: 750; }
.sheet-cancel { color: var(--text-sub); border: 1rpx solid var(--border); }
.sheet-submit { color: #fff; background: var(--primary); }
.state { min-height: 420rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 25rpx; }
.error-state { flex-direction: column; gap: 18rpx; }
.retry { min-height: 66rpx; padding: 0 28rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: 15rpx; font-weight: 700; }
.retry.compact { min-height: 54rpx; padding: 0 20rpx; font-size: 21rpx; }
.empty-card { padding: 76rpx 0; }
.more-error { padding: 18rpx 0 28rpx; display: flex; align-items: center; justify-content: center; gap: 16rpx; color: var(--text-sub); font-size: 21rpx; }
.loading-more { display: block; padding: 24rpx 0; color: var(--text-dim); text-align: center; font-size: 21rpx; }
.skeleton-card { overflow: hidden; }
.skeleton-line { height: 24rpx; border-radius: 8rpx; background: var(--bg-2); }
.skeleton-line.wide { width: 72%; }
.skeleton-line.short { width: 36%; margin-top: 14rpx; }
.skeleton-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24rpx; margin-top: 40rpx; }
@media (prefers-reduced-motion: no-preference) {
  .skeleton-card { animation: skeleton-pulse 1.25s ease-in-out infinite alternate; }
}
@keyframes skeleton-pulse { from { opacity: .55; } to { opacity: 1; } }
</style>
