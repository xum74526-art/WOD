<template>
  <view class="page">
    <AppNavBar :title="t('rechargeOrders')" />

    <view class="search-panel">
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

    <view class="filter-scroll">
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

    <scroll-view scroll-y class="body" @scrolltolower="loadMore">
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
            <text class="credit-value">{{ formatNumber(order.card_hours, { maximumFractionDigits: 6 }) }} {{ t('cardHour') }}</text>
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

        <view v-if="rechargeCanQuery(order) || rechargeCanCancel(order) || commerce.directTradeEnabled" class="order-actions">
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
          <DirectTradeRechargeRestartAction v-if="commerce.directTradeEnabled" :order="order" />
        </view>
      </view>

      <view v-if="loadError && orders.length" class="more-error">
        <text>{{ t('rechargeHistoryLoadFailed') }}</text>
        <view class="retry compact" role="button" @tap="loadMore">{{ t('retry') }}</view>
      </view>
      <text v-else-if="loading && orders.length" class="loading-more">{{ t('loading') }}</text>
      <text v-else-if="orders.length && !hasMore" class="loading-more">{{ t('allLoaded') }}</text>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import {
  cancelRechargePayment,
  getRechargePayments,
  queryRechargePayment,
  type RechargePaymentOrder,
} from '@/api/wallet'
import AppIcon from '@/components/AppIcon.vue'
import AppNavBar from '@/components/AppNavBar.vue'
import EmptyState from '@/components/EmptyState.vue'
import DirectTradeRechargeRestartAction from '@/components/direct-trade/DirectTradeRechargeRestartAction.vue'
import { useI18nStore } from '@/store/i18n'
import { useCommerceStore } from '@/store/commerce'
import { formatMoney, formatNumber } from '@/utils/format'
import { rechargeCanCancel, rechargeCanQuery, rechargeHistoryPresentation } from '@/utils/recharge-payment'
import { displayBusinessReference } from '@/utils/display-reference'

type RechargeStatusFilter = '' | 'pending' | 'paid' | 'review' | 'refund_pending' | 'refund_unknown' | 'refunded' | 'canceled' | 'expired' | 'failed'

const { t, tr } = useI18nStore()
const commerce = useCommerceStore()
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

function statusLabel(order: RechargePaymentOrder): string {
  return rechargeHistoryPresentation(order).labelKey
}

function statusTone(order: RechargePaymentOrder): string {
  return rechargeHistoryPresentation(order).tone
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

function loadMore() {
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

onShow(reload)
</script>

<style lang="scss" scoped>
.page { width: 100%; height: 100vh; height: 100dvh; overflow: hidden; background: var(--bg); display: flex; flex-direction: column; box-sizing: border-box; }
.search-panel { width: calc(100% - 64rpx); min-width: 0; flex: none; display: grid; grid-template-columns: minmax(0, 1fr) 104rpx; gap: 12rpx; margin: 0 32rpx; padding: 22rpx 0 12rpx; box-sizing: border-box; }
.search-box { min-width: 0; min-height: 72rpx; padding: 0 20rpx; display: flex; align-items: center; gap: 12rpx; color: var(--text-sub); background: var(--input-bg); border: 1rpx solid var(--border); border-radius: 16rpx; }
.search-input { width: 0; min-width: 0; flex: 1; height: 72rpx; color: var(--text); font-size: 23rpx; font-variant-numeric: tabular-nums; }
.search-placeholder { color: var(--text-dim); }
.search-clear { flex: none; min-height: 52rpx; display: flex; align-items: center; color: var(--text-sub); font-size: 21rpx; }
.search-button { width: 104rpx; min-height: 72rpx; display: flex; align-items: center; justify-content: center; color: #fff; background: var(--primary); border-radius: 16rpx; font-size: 24rpx; font-weight: 700; }
.search-button:active, .query-button:active, .cancel-button:active, .restart-button:active, .retry:active, .order-number-action:active { transform: scale(.98); }
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
.query-button, .cancel-button, .restart-button { min-height: 64rpx; padding: 0 22rpx; display: flex; align-items: center; justify-content: center; border-radius: 15rpx; font-size: 22rpx; font-weight: 700; }
.query-button { color: var(--primary); border: 1rpx solid var(--primary); }
.cancel-button { color: var(--down); border: 1rpx solid var(--down); }
.restart-button { color: #fff; background: var(--primary); border: 1rpx solid var(--primary); }
.query-button.disabled, .cancel-button.disabled, .restart-button.disabled { opacity: .48; }
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
