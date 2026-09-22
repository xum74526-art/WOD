<template>
  <view class="page">
    <AppNavBar :title="t('withdrawalRecords')" />
    <view class="filter-scroll">
      <scroll-view scroll-x class="filter-inner" :show-scrollbar="false">
        <view class="filter-row">
          <view v-for="item in filters" :key="item.value" class="filter-chip" :class="{ active: filter === item.value }" @tap="changeFilter(item.value)">{{ t(item.label) }}</view>
        </view>
      </scroll-view>
    </view>
    <scroll-view scroll-y class="body" @scrolltolower="loadMore">
      <view v-if="loading && !orders.length" class="state">{{ t('loading') }}</view>
      <view v-else-if="loadError && !orders.length" class="state error-state">
        <text>{{ t('withdrawalListLoadFailed') }}</text>
        <view class="retry" @tap="reload">{{ t('retry') }}</view>
      </view>
      <view v-else-if="!orders.length" class="card empty"><EmptyState :text="t('noWithdrawalRecords')" /></view>

      <view v-for="order in orders" :key="order.id" class="card order-card" @tap="openDetail(order.id)">
        <view class="order-head">
          <view>
            <text class="order-no">{{ displayBusinessReference(order.order_no) }}</text>
            <text class="order-time">{{ formatDate(order.created_at || undefined) }}</text>
          </view>
          <text class="status" :class="statusTone(order.status)">{{ t(statusLabel(order.status)) }}</text>
        </view>
        <view class="amount-row">
          <view><text class="amount-label">{{ t('withdrawCardHours') }}</text><text class="amount-main">{{ fmtCardHours(order.amount_card_hours) }} {{ t('cardHour') }}</text></view>
          <view class="arrival"><text class="amount-label">{{ t('estimatedArrival') }}</text><text class="amount-cny">¥{{ formatMoney(order.net_amount_cny) }}</text></view>
        </view>
        <view class="order-foot">
          <text>{{ tr(order.bank_card.bank_name) }} · {{ order.bank_card.card_number }}</text>
          <text class="detail-link">{{ t('viewDetail') }} ›</text>
        </view>
      </view>
      <text v-if="loading && orders.length" class="loading-more">{{ t('loading') }}</text>
      <text v-else-if="orders.length && orders.length >= total" class="loading-more">{{ t('allLoaded') }}</text>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getWithdrawals, type WithdrawalOrder, type WithdrawalStatus } from '@/api/withdrawal'
import AppNavBar from '@/components/AppNavBar.vue'
import EmptyState from '@/components/EmptyState.vue'
import { useI18nStore } from '@/store/i18n'
import { fmtCardHours, formatDate, formatMoney } from '@/utils/format'
import { navigateTo as nav } from '@/utils/nav'
import { displayBusinessReference } from '@/utils/display-reference'

const { t, tr } = useI18nStore()
const filter = ref<WithdrawalStatus | ''>('')
const orders = ref<WithdrawalOrder[]>([])
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const loadError = ref(false)
const filters: Array<{ value: WithdrawalStatus | ''; label: string }> = [
  { value: '', label: 'all' }, { value: 'reviewing', label: 'statusReviewing' },
  { value: 'manual_payment_pending', label: 'statusManualPaymentPending' }, { value: 'paid', label: 'statusPaid' },
  { value: 'rejected', label: 'statusRejected' },
]

function statusLabel(status: WithdrawalStatus) {
  return ({ reviewing: 'statusReviewing', manual_payment_pending: 'statusManualPaymentPending', paid: 'statusPaid', rejected: 'statusRejected', failed: 'statusFailed', canceled: 'statusCanceled' })[status]
}
function statusTone(status: WithdrawalStatus) {
  return status === 'paid' ? 'success' : ['rejected', 'failed', 'canceled'].includes(status) ? 'danger' : status === 'manual_payment_pending' ? 'pending' : 'reviewing'
}
async function fetchPage(reset = false) {
  if (loading.value || (!reset && orders.value.length >= total.value && total.value > 0)) return
  loading.value = true; loadError.value = false
  const nextPage = reset ? 1 : page.value
  try {
    const result = await getWithdrawals({ page: nextPage, page_size: 20, status_filter: filter.value || undefined })
    orders.value = reset ? result.items : [...orders.value, ...result.items]
    total.value = result.total
    page.value = nextPage + 1
  } catch { loadError.value = true }
  finally { loading.value = false }
}
function reload() { orders.value = []; total.value = 0; page.value = 1; void fetchPage(true) }
function loadMore() { void fetchPage(false) }
function changeFilter(value: WithdrawalStatus | '') { filter.value = value; reload() }
function openDetail(id: number) { nav(`/pages/withdrawals/detail?id=${id}`) }
onShow(reload)
</script>

<style lang="scss" scoped>
.page { height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.filter-scroll { flex: none; padding: 20rpx 0 12rpx; background: var(--bg); }
.filter-inner { width: 100%; white-space: nowrap; }
.filter-row { display: inline-flex; gap: 12rpx; padding: 0 32rpx; }
.filter-chip { min-height: 64rpx; padding: 0 24rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); background: var(--card); border: 1rpx solid var(--border); border-radius: 999rpx; font-size: 23rpx; }
.filter-chip.active { color: var(--primary); background: var(--primary-soft); border-color: var(--primary); font-weight: 700; }
.body { flex: 1; padding: 12rpx 32rpx calc(120rpx + var(--safe-bottom)); box-sizing: border-box; }
.card { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }
.state { min-height: 420rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 25rpx; }
.error-state { flex-direction: column; gap: 18rpx; }
.retry { min-height: 66rpx; padding: 0 28rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: 16rpx; font-weight: 700; }
.empty { padding: 80rpx 0; margin-top: 12rpx; }
.order-card { padding: 26rpx 28rpx; margin-bottom: 16rpx; }
.order-head, .amount-row, .order-foot { display: flex; align-items: center; justify-content: space-between; gap: 18rpx; }
.order-no { display: block; color: var(--text); font-size: 24rpx; font-weight: 700; font-variant-numeric: tabular-nums; }
.order-time { display: block; color: var(--text-dim); font-size: 20rpx; margin-top: 5rpx; }
.status { flex: none; padding: 7rpx 14rpx; border-radius: 999rpx; font-size: 20rpx; font-weight: 700; }
.status.reviewing { color: var(--primary); background: var(--primary-soft); }
.status.pending { color: #a16207; background: rgba(245,158,11,.12); }
.status.success { color: var(--up); background: var(--up-soft); }
.status.danger { color: var(--down); background: var(--down-soft); }
.amount-row { padding: 22rpx 0; margin-top: 18rpx; border-top: 1rpx solid var(--divider); border-bottom: 1rpx solid var(--divider); align-items: flex-end; }
.amount-label { display: block; color: var(--text-sub); font-size: 20rpx; }
.amount-main { display: block; color: var(--text); font-size: 31rpx; font-weight: 800; margin-top: 7rpx; }
.arrival { text-align: right; }
.amount-cny { display: block; color: var(--primary); font-size: 31rpx; font-weight: 800; margin-top: 7rpx; }
.order-foot { color: var(--text-sub); font-size: 21rpx; padding-top: 18rpx; }
.detail-link { color: var(--primary); font-weight: 700; }
.loading-more { display: block; color: var(--text-dim); text-align: center; font-size: 21rpx; padding: 24rpx 0; }
</style>
