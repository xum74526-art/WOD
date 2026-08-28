<template>
  <view class="page">
    <AppNavBar :title="t('k_c66f18b9')">
      <template #right><text class="nav-switch" @tap="switchBack">{{ t('切回个人') }}</text></template>
    </AppNavBar>
    <view class="shell">
      <view v-if="loadError" class="load-error">
        <text>{{ t('supplierLoadFailedDesc') }}</text>
        <text class="load-retry" @tap="load">{{ t('retry') }}</text>
      </view>
      <!-- 收益看板 -->
      <view class="card hero">
        <view class="hero-row">
          <view class="hero-main">
            <text class="hero-label">{{ t('今日收入（卡时）') }}</text>
            <text class="hero-val up">{{ fmtCHn(dash?.today_revenue) }}</text>
          </view>
          <view class="hero-side">
            <text class="hs-label">{{ t('累计收入') }}</text>
            <text class="hs-val">{{ fmtCH(dash?.total_revenue) }}</text>
          </view>
        </view>
        <view class="hero-grid">
          <view class="hg-item"><text class="hg-l">{{ t('在售设备') }}</text><text class="hg-v">{{ dash?.product_count ?? 0 }}</text></view>
          <view class="hg-item"><text class="hg-l">{{ t('可租总量') }}</text><text class="hg-v">{{ dash?.total_stock ?? 0 }}</text></view>
          <view class="hg-item"><text class="hg-l">{{ t('待交付') }}</text><text class="hg-v up">{{ dash?.pending_orders ?? 0 }}</text></view>
          <view class="hg-item"><text class="hg-l">{{ t('完成订单') }}</text><text class="hg-v">{{ dash?.completed_orders ?? 0 }}</text></view>
        </view>
      </view>

      <!-- 同一账号的个人购买返佣，与商家销售返佣分开统计。 -->
      <view v-if="personalRebate" class="card rebate-card" @tap="go('/pages/rebate/index')">
        <view class="rb-title-row">
          <text class="rb-title">{{ t('personalPurchaseRebate') }}</text>
          <text v-if="personalRebate.reward_mode === 'test_card_hours'" class="rb-mode">{{ t('closedTestRewardBadge') }}</text>
        </view>
        <view class="rb-row">
          <view class="rb-item">
            <text class="rb-v up">{{ fmtCHn(personalRebate.pending_rebate) }}</text>
            <text class="rb-l">{{ t('pendingExpiryRebate') }}</text>
          </view>
          <view class="rb-item">
            <text class="rb-v">{{ formatNumber(personalRebate.current_rate) }}%</text>
            <text class="rb-l">{{ t('personalPurchaseRebateTier') }}</text>
          </view>
          <view class="rb-item">
            <text class="rb-v">{{ fmtCHn(personalRebate.month_spent) }}</text>
            <text class="rb-l">{{ t('confirmedUsagePurchasesThisMonth') }}</text>
          </view>
        </view>
        <text class="rb-hint">{{ tr(personalRebate.next_tier_hint) }}</text>
      </view>

      <!-- 商家销售返佣卡片 -->
      <view v-if="rebate" class="card rebate-card" @tap="go('/pages/supplier/rebate')">
        <view class="rb-title-row">
          <text class="rb-title">{{ t('merchantSalesRebate') }}</text>
          <text v-if="rebate.reward_mode === 'test_card_hours'" class="rb-mode">{{ t('closedTestRewardBadge') }}</text>
        </view>
        <view class="rb-row">
          <view class="rb-item">
            <text class="rb-v up">{{ fmtCHn(rebate.month_rebated) }}</text>
            <text class="rb-l">{{ t('本月已返（卡时）') }}</text>
          </view>
          <view class="rb-item">
            <text class="rb-v">{{ formatNumber(rebate.current_rate) }}%</text>
            <text class="rb-l">{{ t('merchantSalesRebateTier') }}</text>
          </view>
          <view class="rb-item">
            <text class="rb-v">{{ fmtCHn(rebate.month_sales) }}</text>
            <text class="rb-l">{{ t('confirmedSalesThisMonth') }}</text>
          </view>
        </view>
        <text class="rb-hint">{{ tr(rebate.next_tier_hint) }}</text>
      </view>

      <!-- 5模块入口 -->
      <view class="modules">
        <view class="mod-item" @tap="go('/pages/supplier/devices')">
          <view class="mod-icon"><AppIcon name="gpu" :size="48" /></view>
          <text class="mod-text">{{ t('merchantResourceManagement') }}</text>
          <text class="mod-sub">{{ t('{count} 台设备', { count: dash?.product_count ?? 0 }) }}</text>
        </view>
        <view class="mod-item" @tap="go('/pages/supplier/revenue')">
          <view class="mod-icon"><AppIcon name="wallet" :size="48" /></view>
          <text class="mod-text">{{ t('收益结算') }}</text>
          <text class="mod-sub">{{ fmtCH(dash?.total_revenue) }}</text>
        </view>
        <view class="mod-item" @tap="go('/pages/supplier/orders')">
          <view class="mod-icon"><AppIcon name="order" :size="48" /></view>
          <text class="mod-text">{{ t('订单客户') }}</text>
          <text class="mod-sub">{{ t('{count} 个订单', { count: dash?.completed_orders ?? 0 }) }}</text>
        </view>
        <view class="mod-item" @tap="go('/pages/supplier/stats')">
          <view class="mod-icon"><AppIcon name="revenue" :size="48" /></view>
          <text class="mod-text">{{ t('数据运维') }}</text>
          <text class="mod-sub">{{ t('统计分析') }}</text>
        </view>
        <view class="mod-item" @tap="go('/pages/supplier/rebate')">
          <view class="mod-icon"><AppIcon name="coin" :size="48" /></view>
          <text class="mod-text">{{ t('销售返佣') }}</text>
          <text class="mod-sub">{{ t('{rate}% 返还', { rate: formatNumber(rebate?.current_rate ?? 5) }) }}</text>
        </view>
        <view class="mod-item" @tap="go('/pages/supplier/settings')">
          <view class="mod-icon"><AppIcon name="settings" :size="48" /></view>
          <text class="mod-text">{{ t('基础设置') }}</text>
          <text class="mod-sub">{{ t('店铺资料') }}</text>
        </view>
      </view>

      <!-- 7天收益趋势 -->
      <SectionHeader :title="t('收益趋势（7天）')" />
      <view class="card chart-card" v-if="dash?.trend?.length">
        <Chart :points="dash.trend" value-key="amount" :height="140" />
      </view>
      <view v-else class="card ph">{{ t('暂无收益数据') }}</view>

      <!-- 设备概览 -->
      <SectionHeader :title="t('设备概览')">
        <template #extra><text @tap="go('/pages/supplier/devices')">{{ t('全部') }} ›</text></template>
      </SectionHeader>
      <view v-if="!dash?.devices?.length" class="card ph">{{ t('暂无设备') }}</view>
      <view v-for="d in dash?.devices" :key="d.id" class="card drow" @tap="go('/pages/supplier/devices')">
        <view class="dl">
          <view class="dl-row">
            <text class="dn">{{ tr(d.name) }}</text>
            <view class="dot" :class="d.status"></view>
          </view>
            <text class="dg">{{ d.gpu_model }} · {{ localizeRegionName(d.region, i18n.lang) }} · {{ t('可租 {count}', { count: d.stock }) }}</text>
        </view>
        <view class="dr"><text class="dv up">{{ fmtCH(d.price) }}/h</text></view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getDashboard, getSupplierRebate, type SupplierRebate } from '@/api/supplier'
import { getRebateSummary, type RebateSummary } from '@/api/user'
import { useUserStore } from '@/store/user'
import { formatNumber, fmtCH, fmtCHr, fmtCHn, toCardHours } from '@/utils/format'
import { navigateTo as go } from '@/utils/nav'
import AppNavBar from '@/components/AppNavBar.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import Chart from '@/components/Chart.vue'
import AppIcon from '@/components/AppIcon.vue'
import { useI18nStore } from '@/store/i18n'
import { localizeRegionName } from '@/utils/region-name'

const i18n = useI18nStore()
const { t, tr } = i18n
const userStore = useUserStore()
const dash = ref<Awaited<ReturnType<typeof getDashboard>> | null>(null)
const rebate = ref<SupplierRebate | null>(null)
const personalRebate = ref<RebateSummary | null>(null)
const loadError = ref(false)

async function load() {
  loadError.value = false
  const [dashboardResult, rebateResult, personalRebateResult] = await Promise.allSettled([
    getDashboard(),
    getSupplierRebate(),
    getRebateSummary(),
  ])
  dash.value = dashboardResult.status === 'fulfilled' ? dashboardResult.value : null
  rebate.value = rebateResult.status === 'fulfilled' ? rebateResult.value : null
  personalRebate.value = personalRebateResult.status === 'fulfilled' ? personalRebateResult.value : null
  loadError.value = [dashboardResult, rebateResult, personalRebateResult].some((result) => result.status === 'rejected')
}
onShow(() => load())
async function switchBack() {
  try { await userStore.switchRole(); uni.switchTab({ url: '/pages/profile/index' }) } catch {}
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx 132rpx; }
.nav-switch { color: var(--primary); font-size: 24rpx; }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--card-border); }
.load-error { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; padding: 20rpx 24rpx; margin: 24rpx 0 0; color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); font-size: 23rpx; line-height: 1.5; }
.load-retry { flex-shrink: 0; color: var(--primary); font-weight: 700; min-height: 64rpx; display: flex; align-items: center; }
.hero { padding: 36rpx 32rpx; margin: 24rpx 0; background: var(--card); border: none; }
.hero-row { display: flex; justify-content: space-between; align-items: flex-end; }
.hero-main { flex: 1; }
.hero-label { color: var(--text-sub); font-size: 22rpx; }
.hero-val { display: block; color: var(--text); font-size: 56rpx; font-weight: 800; font-variant-numeric: tabular-nums; }
.hero-side { text-align: right; }
.hs-label { color: var(--text-sub); font-size: 22rpx; display: block; }
.hs-val { color: var(--text); font-size: 32rpx; font-weight: 700; display: block; margin-top: 4rpx; font-variant-numeric: tabular-nums; }
.hero-grid { display: flex; gap: 16rpx; margin-top: 28rpx; }
.hg-item { flex: 1; text-align: center; background: rgba(255,255,255,0.3); border-radius: 12rpx; padding: 16rpx 0; }
.hg-l { color: var(--text-sub); font-size: 20rpx; display: block; }
.hg-v { color: var(--text); font-size: 28rpx; font-weight: 700; display: block; margin-top: 4rpx; }
.up { color: var(--up); }
.rebate-card { padding: 28rpx 32rpx; margin: 20rpx 0; }
.rb-title-row { display: flex; align-items: center; justify-content: space-between; gap: 16rpx; margin-bottom: 20rpx; }
.rb-title { color: var(--text); font-size: 26rpx; font-weight: 700; }
.rb-mode { color: var(--primary); background: var(--card-border); border-radius: 999rpx; padding: 6rpx 14rpx; font-size: 19rpx; }
.rb-row { display: flex; }
.rb-item { flex: 1; text-align: center; }
.rb-item + .rb-item { border-left: 1rpx solid var(--card-border); }
.rb-v { display: block; color: var(--text); font-size: 36rpx; font-weight: 800; font-variant-numeric: tabular-nums; }
.rb-v.up { color: var(--up); }
.rb-l { display: block; color: var(--text-sub); font-size: 20rpx; margin-top: 6rpx; }
.rb-hint { display: block; color: var(--primary); font-size: 22rpx; margin-top: 16rpx; text-align: center; }
.modules { display: flex; flex-wrap: wrap; gap: 16rpx; margin: 24rpx 0; }
.mod-item { width: 31%; display: flex; flex-direction: column; align-items: center; padding: 28rpx 0; background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--card-border); }
.mod-icon { width: 80rpx; height: 80rpx; border-radius: 40rpx; background: var(--primary-soft); display: flex; align-items: center; justify-content: center; margin-bottom: 12rpx; }
.mod-text { color: var(--text); font-size: 24rpx; font-weight: 600; }
.mod-sub { color: var(--text-sub); font-size: 20rpx; margin-top: 4rpx; }
.chart-card { padding: 24rpx 16rpx; margin-bottom: 24rpx; }
.ph { padding: 40rpx; text-align: center; color: var(--text-sub); font-size: 26rpx; }
.drow { display: flex; justify-content: space-between; align-items: center; padding: 32rpx; margin-bottom: 16rpx; }
.dl-row { display: flex; align-items: center; gap: 16rpx; }
.dn { color: var(--text); font-size: 30rpx; font-weight: 600; }
.dot { width: 16rpx; height: 16rpx; border-radius: 8rpx; }
.dot.online { background: var(--up); }
.dot.offline { background: var(--text-dim); }
.dg { display: block; color: var(--text-sub); font-size: 24rpx; margin-top: 12rpx; }
.dv { font-size: 32rpx; font-weight: 700; font-variant-numeric: tabular-nums; }
</style>
