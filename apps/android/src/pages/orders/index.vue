<template>
  <view class="page">
    <AppNavBar :title="t('orders')" />
    <view class="seg-wrap">
      <SegmentedControl v-model="tab" :items="['全部', '待交付', '待确认', '已完成']" />
    </view>
    <scroll-view scroll-y class="body">
      <view v-if="loading && !orders.length" class="state">{{ t('loading') }}</view>
      <view v-else-if="loadError" class="load-error">
        <text>{{ t('listLoadFailedDesc') }}</text>
        <text class="load-retry" @tap="fetchList">{{ t('retry') }}</text>
      </view>
      <template v-else-if="orders.length">
        <view v-for="o in orders" :key="o.id" class="card order" @tap="goDetail(o.id)">
          <view class="o-top">
            <view class="o-name-wrap">
              <text class="o-name">{{ localizeProductName(o.product_name || t('算力订单'), i18n.lang) }}</text>
              <text class="o-no">{{ t('orderNo') }} {{ displayBusinessReference(o.order_no) || ('#' + o.id) }}</text>
            </view>
            <StatusBadge :text="statusMeta(o.status).text" :type="statusMeta(o.status).type" />
          </view>
          <view class="o-meta">
            <text class="o-cycle">{{ orderDuration(o) }}</text>
            <text class="o-dot">·</text>
            <text class="o-gpu">{{ o.gpu_model || '-' }}</text>
            <text class="o-gpu">× {{ o.quantity || 1 }}</text>
          </view>
          <view class="o-bottom">
            <view class="o-amount">
              <text class="o-amt-label">{{ t('cardHour') }}</text>
              <text class="o-amt-val">{{ fmtCardHours(o.payable_amount_card_hours ?? o.amount_card_hours ?? o.amount) }}</text>
            </view>
            <view v-if="o.revenue_settlement_enabled" class="o-amount">
              <text class="o-amt-label">{{ t('cumulativeRevenue') }}</text>
              <text class="o-amt-val up">{{ fmtCardHours(o.accumulated_revenue ?? 0) }}</text>
            </view>
            <view v-else class="o-amount">
              <text class="o-amt-label">{{ t('revenueSettlementStatus') }}</text>
              <text class="o-amt-val dim">{{ t('notAvailable') }}</text>
            </view>
            <view class="o-amount">
              <text class="o-amt-label">{{ t('k_43b510ed') }}</text>
              <text class="o-amt-val">{{ orderRemaining(o) }}</text>
            </view>
          </view>
        </view>
      </template>
      <EmptyState v-else text="暂无订单">
        <AppIcon name="order" :size="56" />
      </EmptyState>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getOrders, type OrderItem } from '@/api/order'
import { fmtCardHours } from '@/utils/format'
import AppNavBar from '@/components/AppNavBar.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import EmptyState from '@/components/EmptyState.vue'
import AppIcon from '@/components/AppIcon.vue'
import { navigateTo as nav } from '@/utils/nav'
import { useI18nStore } from '@/store/i18n'
import { localizeProductName } from '@/utils/localize-content'
import { displayBusinessReference } from '@/utils/display-reference'

const i18n = useI18nStore()
const { t } = i18n
const FILTERS = ['', 'paid', 'delivering', 'completed'] as const
const tab = ref(0)
const orders = ref<OrderItem[]>([])
const loading = ref(true)
const loadError = ref(false)

function isHourlyOrder(order: OrderItem): boolean {
  return order.purchase_unit === 'hour' || Number(order.duration_hours ?? order.purchase_hours) > 0
}
function orderDuration(order: OrderItem): string {
  if (isHourlyOrder(order)) return t('hoursValue', { count: Number(order.duration_hours ?? order.purchase_hours ?? 0) })
  return t('{days} 天', { days: Number(order.cycle_days || 0) })
}
function orderRemaining(order: OrderItem): string {
  if (isHourlyOrder(order) && order.remaining_hours != null) return t('hoursValue', { count: order.remaining_hours })
  return t('{days} 天', { days: order.remaining_days ?? 0 })
}

function statusMeta(s?: string) {
  if (s === 'paid') return { text: '待交付', type: 'running' as const }
  if (s === 'delivering') return { text: '待确认', type: 'running' as const }
  if (s === 'completed') return { text: '已完成', type: 'done' as const }
  if (s === 'running') return { text: '运行中', type: 'running' as const }
  if (s === 'canceled') return { text: '已取消', type: 'canceled' as const }
  if (s === 'expired') return { text: '已到期', type: 'expired' as const }
  return { text: s || '待处理', type: 'default' as const }
}

async function fetchList() {
  loading.value = true
  loadError.value = false
  orders.value = []
  try {
    const filter = FILTERS[tab.value]
    orders.value = await getOrders(filter || undefined)
  } catch {
    loadError.value = true
  }
  loading.value = false
}

onShow(() => fetchList())
watch(tab, () => fetchList())

function goDetail(id: number) {
  nav(`/pages/order/detail?id=${id}`)
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.seg-wrap { padding: 0 32rpx 16rpx; }
.body { flex: 1; padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.state { color: var(--text-sub); text-align: center; padding: 120rpx 0; font-size: 28rpx; }
.card { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }

.order { padding: 32rpx; margin-bottom: 24rpx; }
.o-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 16rpx; }
.o-name-wrap { flex: 1; min-width: 0; }
.o-name { color: var(--text); font-size: 32rpx; font-weight: 600; display: block; }
.o-no { color: var(--text-dim); font-size: 24rpx; margin-top: 8rpx; display: block; font-variant-numeric: tabular-nums; }
.o-meta { display: flex; align-items: center; gap: 12rpx; margin-top: 20rpx; }
.o-cycle { color: var(--primary); font-size: 26rpx; background: var(--primary-soft); padding: 6rpx 16rpx; border-radius: var(--radius); }
.o-dot { color: var(--text-dim); font-size: 26rpx; }
.o-gpu { color: var(--text-sub); font-size: 26rpx; }
.o-bottom { display: flex; margin-top: 28rpx; padding-top: 24rpx; border-top: 1rpx solid var(--divider); }
.o-amount { flex: 1; display: flex; flex-direction: column; gap: 8rpx; }
.o-amt-label { color: var(--text-sub); font-size: 22rpx; }
.o-amt-val { color: var(--text); font-size: 30rpx; font-weight: 600; font-variant-numeric: tabular-nums; }
.o-amt-val.up { color: var(--up); }
.o-amt-val.dim { color: var(--text-dim); font-size: 24rpx; }
.load-error { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; padding: 20rpx 24rpx; color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); font-size: 23rpx; line-height: 1.5; }
.load-retry { flex-shrink: 0; color: var(--primary); font-weight: 700; min-height: 64rpx; display: flex; align-items: center; }
</style>
