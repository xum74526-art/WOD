<template>
  <view class="page">
    <AppNavBar :title="t('k_07e455b2')" />
    <view class="seg-wrap">
      <SegmentedControl v-model="tab" :items="['全部', '充值', '提现', '支付', '收益', '退款']" />
    </view>
    <scroll-view scroll-y class="body" @scrolltolower="onScrollLower">
      <view v-if="loadError && !items.length" class="load-error">
        <text>{{ t('dataUnavailable') }}</text>
        <view class="load-retry" role="button" @tap="fetchPage(true)">{{ t('retry') }}</view>
      </view>
      <view v-else-if="!items.length && !loading" class="empty-wrap">
        <EmptyState text="暂无流水记录">
          <AppIcon name="wallet" :size="56" />
        </EmptyState>
      </view>
      <view v-else class="list">
        <view v-for="(it, i) in items" :key="it.id" class="card item" :class="{ last: i === items.length - 1 }">
          <view class="it-top">
            <text class="it-type">{{ typeLabel(it.type) }}</text>
            <text class="it-amt" :class="it.direction === 'in' ? 'up' : 'down'">
              {{ it.direction === 'in' ? '+' : '-' }}{{ formatSettlementCny(it.amount) }}
            </text>
          </view>
          <view class="it-mid">
            <text class="it-remark" v-if="it.remark">{{ tr(it.remark) }}</text>
            <text class="it-remark dim" v-else>{{ t('{type}流水', { type: typeLabel(it.type) }) }}</text>
          </view>
          <view class="it-bottom">
            <text class="it-time">{{ formatDate(it.created_at) }}</text>
            <text class="it-bal">{{ t('walletBalanceLabel') }} {{ formatSettlementCny(it.balance_after) }}</text>
          </view>
        </view>
        <view v-if="loading" class="load-more">{{ t('loading') }}</view>
        <view v-else-if="!hasMore && items.length" class="load-more">{{ t("noMore") }}</view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getLedger, type LedgerItem } from '@/api/wallet'
import { formatDate, formatSettlementCny } from '@/utils/format'
import AppNavBar from '@/components/AppNavBar.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import EmptyState from '@/components/EmptyState.vue'
import AppIcon from '@/components/AppIcon.vue'
import { useI18nStore } from '@/store/i18n'

const { t, tr } = useI18nStore()
const FILTERS = ['', 'recharge', 'withdraw', 'pay', 'revenue', 'refund'] as const
const tab = ref(0)

const items = ref<LedgerItem[]>([])
const page = ref(1)
const hasMore = ref(true)
const loading = ref(false)
const loadError = ref(false)
let loadGeneration = 0

function typeLabel(type?: string) {
  switch (type) {
    case 'recharge': return t('充值')
    case 'withdraw': return t('提现')
    case 'pay': return t('支付')
    case 'revenue': return t('收益')
    case 'test_revenue': return t('historicalTestRevenue')
    case 'test_reward': return t('historicalTestReward')
    case 'validation_credit': return t('functionalValidationCredit')
    case 'refund': return t('退款')
    default: return type ? tr(type) : tr('流水')
  }
}

async function fetchPage(reset = false) {
  if (!reset && loading.value) return
  if (reset) {
    loadGeneration++
    items.value = []
    page.value = 1
    hasMore.value = true
    loadError.value = false
  }
  const generation = loadGeneration
  loading.value = true
  const p = reset ? 1 : page.value
  try {
    const filter = FILTERS[tab.value]
    const res = await getLedger({ type_filter: filter || undefined, page: p, page_size: 20 })
    if (generation !== loadGeneration) return
    items.value = reset ? res.items : [...items.value, ...res.items]
    hasMore.value = items.value.length < res.total
    page.value = p + 1
  } catch {
    /* request 已 toast */
    if (generation === loadGeneration && p === 1) loadError.value = true
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

onLoad(() => fetchPage(true))
watch(tab, () => fetchPage(true))

function onScrollLower() {
  if (hasMore.value && !loading.value) fetchPage(false)
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.seg-wrap { padding: 0 32rpx 16rpx; }
.body { flex: 1; padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.empty-wrap { padding-top: 40rpx; }
.load-error { min-height: 320rpx; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 18rpx; color: var(--text-sub); font-size: 26rpx; }
.load-retry { min-height: 68rpx; padding: 0 28rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: var(--radius); font-weight: 700; }
.list { display: flex; flex-direction: column; gap: 16rpx; }
.card { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }

.item { padding: 28rpx 32rpx; }
.it-top { display: flex; justify-content: space-between; align-items: center; }
.it-type { color: var(--text); font-size: 30rpx; font-weight: 600; }
.it-amt { font-size: 32rpx; font-weight: 700; font-variant-numeric: tabular-nums; }
.it-amt.up { color: var(--up); }
.it-amt.down { color: var(--down); }
.it-mid { margin-top: 12rpx; }
.it-remark { color: var(--text-sub); font-size: 26rpx; }
.it-remark.dim { color: var(--text-dim); }
.it-bottom { display: flex; justify-content: space-between; align-items: center; margin-top: 16rpx; }
.it-time { color: var(--text-dim); font-size: 24rpx; font-variant-numeric: tabular-nums; }
.it-bal { color: var(--text-sub); font-size: 24rpx; font-variant-numeric: tabular-nums; }

.load-more { text-align: center; color: var(--text-dim); font-size: 24rpx; padding: 32rpx 0; }
</style>
