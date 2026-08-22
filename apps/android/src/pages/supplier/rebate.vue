<template>
  <view class="page">
    <AppNavBar :title="t('k_ae9229c7')" />
    <view class="shell">
      <view v-if="loading" class="load-state">{{ t('loading') }}</view>
      <view v-else-if="loadError" class="load-state load-error">
        <text>{{ t('dataUnavailable') }}</text>
        <view class="load-retry" role="button" @tap="load">{{ t('retry') }}</view>
      </view>
      <template v-else>
      <view v-if="info && !info.rewards_enabled" class="card service-warning">{{ t('rewardServiceUnavailable') }}</view>
      <view v-else-if="info?.reward_mode === 'test_card_hours'" class="card mode-notice">{{ t('closedTestRewardNotice') }}</view>
      <!-- 返佣看板 -->
      <view class="card hero">
        <view class="hero-main">
          <text class="hero-label">{{ t('k_e08bcd4e') }}</text>
          <text class="hero-val up">{{ fmtCHn(info?.month_rebated ?? 0) }}</text>
        </view>
        <view class="hero-grid">
          <view class="hg-item">
          <text class="hg-v">{{ formatNumber(info?.current_rate ?? 5) }}%</text>
            <text class="hg-l">{{ t('k_cfc752a6') }}</text>
          </view>
          <view class="hg-item">
            <text class="hg-v">{{ fmtCHn(info?.month_sales ?? 0) }}</text>
            <text class="hg-l">{{ t('k_e1e32957') }}</text>
          </view>
          <view class="hg-item">
            <text class="hg-v">{{ fmtCHn(info?.est_total_rebate ?? 0) }}</text>
            <text class="hg-l">{{ t('k_cc3967b0') }}</text>
          </view>
        </view>
        <text class="hero-hint">{{ tr(info?.next_tier_hint || '') }}</text>
      </view>

      <!-- 阶梯说明 -->
      <SectionHeader :title="t('k_88c1784e')" />
      <view class="card tier-card">
        <view class="tier-row" v-for="tier in tiers" :key="tier.rate" :class="{ active: (info?.current_rate ?? 5) === tier.rate }">
          <view class="tier-left">
            <text class="tier-rate">{{ formatNumber(tier.rate) }}%</text>
            <text class="tier-range">{{ t(tier.range) }}</text>
          </view>
          <text v-if="(info?.current_rate ?? 5) === tier.rate" class="tier-tag">{{ t('k_48ac4797') }}</text>
        </view>
      </view>

      <!-- 规则说明 -->
      <SectionHeader :title="t('k_9317c0d3')" />
      <view class="card rules-card">
        <view class="rule-item"><text class="dot"></text><text class="rt">{{ t('k_f01375b8') }}</text></view>
        <view class="rule-item"><text class="dot"></text><text class="rt">{{ t('服务费 = 订单卡时 × {rate}%', { rate: formatNumber(info?.service_fee_rate ?? 10) }) }}</text></view>
        <view class="rule-item"><text class="dot"></text><text class="rt">{{ t('返佣 = 服务费 × 对应阶梯比例') }}</text></view>
        <view class="rule-item"><text class="dot"></text><text class="rt">{{ t('k_5b130763') }}</text></view>
        <view class="rule-item"><text class="dot"></text><text class="rt">{{ t('每月返佣上限 {amount} 卡时', { amount: formatNumber(info?.monthly_cap ?? 2000) }) }}</text></view>
        <view class="rule-item"><text class="dot"></text><text class="rt">{{ t('k_c8d65559') }}</text></view>
      </view>

      <!-- 返佣记录 -->
      <SectionHeader :title="t('k_f1398c6d')" />
      <view v-if="!records.length" class="card ph"><EmptyState text="暂无返佣记录" /></view>
      <view v-for="r in records" :key="r.id" class="card rec-row">
        <view class="rec-left">
          <text class="rec-amount">+{{ fmtCH(r.amount) }}</text>
          <text class="rec-date">{{ formatDate(r.created_at) }}</text>
        </view>
        <text class="rec-remark">{{ tr(r.remark) }}</text>
      </view>
      </template>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getSupplierRebate, type SupplierRebate } from '@/api/supplier'
import { getLedger, type LedgerItem } from '@/api/wallet'
import { fmtCH, fmtCHn, formatDate, formatNumber } from '@/utils/format'
import AppNavBar from '@/components/AppNavBar.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import { useI18nStore } from '@/store/i18n'

const { t, tr } = useI18nStore()
const info = ref<SupplierRebate | null>(null)
const records = ref<LedgerItem[]>([])
const loading = ref(true)
const loadError = ref(false)

const tiers = [
  { rate: 5, range: '0 - 10,000 卡时' },
  { rate: 8, range: '10,000 - 50,000 卡时' },
  { rate: 11, range: '50,000 - 100,000 卡时' },
  { rate: 13, range: '100,000 - 200,000 卡时' },
  { rate: 15, range: '200,000+ 卡时' },
]

async function load() {
  loading.value = true
  loadError.value = false
  const [summaryResult, recordsResult] = await Promise.allSettled([
    getSupplierRebate(),
    getLedger({ type_filter: 'supplier_rebate', page: 1, page_size: 20 }),
  ])
  if (summaryResult.status === 'fulfilled') info.value = summaryResult.value
  if (recordsResult.status === 'fulfilled') records.value = recordsResult.value.items
  loadError.value = summaryResult.status === 'rejected' || recordsResult.status === 'rejected'
  loading.value = false
}
onShow(() => load())
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--card-border); }
.load-state { min-height: 420rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 26rpx; }
.load-error { flex-direction: column; gap: 18rpx; }
.load-retry { min-height: 68rpx; padding: 0 28rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: var(--radius); font-weight: 700; }
.service-warning, .mode-notice { padding: 22rpx 26rpx; margin: 24rpx 0 12rpx; color: var(--text-sub); font-size: 22rpx; line-height: 1.6; }
.mode-notice { color: var(--primary); background: var(--card-border); }

.hero { padding: 40rpx 32rpx; margin: 24rpx 0; background: var(--card); border: none; }
.hero-main { margin-bottom: 24rpx; }
.hero-label { color: var(--text-sub); font-size: 24rpx; }
.hero-val { display: block; color: var(--text); font-size: 56rpx; font-weight: 800; margin-top: 8rpx; font-variant-numeric: tabular-nums; }
.hero-grid { display: flex; gap: 16rpx; }
.hg-item { flex: 1; text-align: center; background: rgba(255,255,255,0.3); border-radius: 12rpx; padding: 16rpx 0; }
.hg-l { color: var(--text-sub); font-size: 20rpx; display: block; }
.hg-v { color: var(--text); font-size: 28rpx; font-weight: 700; display: block; margin-bottom: 4rpx; }
.hero-hint { display: block; color: var(--primary); font-size: 22rpx; margin-top: 20rpx; text-align: center; }
.up { color: var(--up); }

.tier-card { padding: 8rpx 32rpx; margin-bottom: 24rpx; }
.tier-row { display: flex; justify-content: space-between; align-items: center; padding: 20rpx 0; border-bottom: 1rpx solid var(--card-border); }
.tier-row:last-child { border-bottom: none; }
.tier-row.active { background: rgba(24,175,196,0.04); border-radius: 8rpx; padding-left: 12rpx; padding-right: 12rpx; margin: 0 -12rpx; }
.tier-left { display: flex; align-items: center; gap: 20rpx; }
.tier-rate { color: var(--text); font-size: 32rpx; font-weight: 800; min-width: 80rpx; }
.tier-row.active .tier-rate { color: var(--primary); }
.tier-range { color: var(--text-sub); font-size: 24rpx; }
.tier-tag { background: var(--primary); color: #fff; font-size: 20rpx; padding: 4rpx 16rpx; border-radius: 8rpx; }

.rules-card { padding: 24rpx 32rpx; margin-bottom: 24rpx; }
.rule-item { display: flex; align-items: flex-start; gap: 16rpx; margin-bottom: 16rpx; }
.rule-item:last-child { margin-bottom: 0; }
.dot { width: 12rpx; height: 12rpx; border-radius: 6rpx; background: var(--primary); flex-shrink: 0; margin-top: 8rpx; }
.rt { color: var(--text); font-size: 24rpx; line-height: 1.6; }

.ph { padding: 60rpx 0; }
.rec-row { display: flex; justify-content: space-between; align-items: center; padding: 24rpx 32rpx; margin-bottom: 12rpx; }
.rec-left { flex: 1; }
.rec-amount { color: var(--up); font-size: 28rpx; font-weight: 700; display: block; }
.rec-date { color: var(--text-dim); font-size: 22rpx; display: block; margin-top: 4rpx; }
.rec-remark { color: var(--text-sub); font-size: 22rpx; text-align: right; max-width: 200rpx; }
</style>
