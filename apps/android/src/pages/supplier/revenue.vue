<template>
  <view class="page">
    <AppNavBar :title="t('k_a1d8f5fb')" />
    <view class="shell">
      <!-- 收益看板 -->
      <view class="card hero">
        <view class="hero-main">
          <text class="hl">{{ t('k_52878214') }}</text>
          <text class="hv up">{{ fmtCH(wallet?.today_revenue) }}</text>
        </view>
        <view class="hero-grid">
          <view class="hg-item"><text class="hg-l">{{ t('k_d00a676b') }}</text><text class="hg-v">{{ fmtCH(wallet?.total_revenue) }}</text></view>
          <view class="hg-item"><text class="hg-l">{{ t('k_c4e8bacf') }}</text><text class="hg-v">{{ fmtCH(wallet?.pending_amount) }}</text></view>
          <view class="hg-item"><text class="hg-l">{{ t('k_f7e76123') }}</text><text class="hg-v up">{{ fmtCH(wallet?.available) }}</text></view>
          <view class="hg-item"><text class="hg-l">{{ t('k_70dbe1ce') }}</text><text class="hg-v">{{ fmtCH(wallet?.withdrawn) }}</text></view>
        </view>
      </view>

      <view class="quick-row">
        <DirectTradeSupplierWithdrawalAction v-if="commerce.withdrawEnabled" />
        <view v-else class="q-btn disabled">{{ t('withdrawalUnavailableShort') }}</view>
        <view class="q-btn ghost" @tap="goDevices">{{ t('k_53ac00e9') }}</view>
      </view>

      <SectionHeader :title="t('k_abcf9282')" />
      <view v-if="loadError" class="load-error">
        <text>{{ t('supplierLoadFailedDesc') }}</text>
        <text class="load-retry" @tap="load">{{ t('retry') }}</text>
      </view>

      <view v-if="wallet?.historical_unreconciled_count" class="audit-note">
        {{ t('历史订单待财务核账（{count} 笔），不会自动计入可提现余额。', { count: wallet.historical_unreconciled_count }) }}
      </view>
      <view v-if="!loadError && !records.length" class="card ph"><EmptyState :text="t('暂无交易记录')" /></view>
      <view v-for="r in records" :key="r.order_no" class="card rrow">
        <view class="rl">
          <text class="rn">{{ localizeProductName(r.product_name, i18n.lang) }}</text>
          <text class="rg">{{ t('买家') }}: {{ tr(r.buyer_name) }} · {{ r.order_no.slice(-8) }} · {{ formatDate(r.created_at || undefined) }}</text>
          <view class="rtags">
            <text class="rtag" v-if="r.purchase_type === 'holding'">{{ t('k_fdeb9cd3') }}</text>
            <text class="rtag" v-else>{{ t('k_ecff77a8') }}</text>
            <text class="rtag status" :class="r.settlement_status">{{ settlementText(r.settlement_status, r.status) }}</text>
          </view>
        </view>
        <view class="rr">
          <text class="rv" :class="{ up: r.settlement_status === 'settled' }">{{ r.settlement_status === 'settled' ? '+' + fmtCH(r.net_income) : r.settlement_status === 'historical_unreconciled' ? t('待财务核账') : t('pendingSettlement') }}</text>
          <text class="rs">{{ t('订单') }} {{ fmtCH(r.amount) }} · {{ t('服务费') }} {{ r.settlement_status === 'settled' ? fmtCH(r.service_fee) : '—' }}</text>
        </view>
      </view>
    </view>

  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getSupplierWallet, getRevenueDetail } from '@/api/supplier'
import { fmtCH, formatDate } from '@/utils/format'
import AppNavBar from '@/components/AppNavBar.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import DirectTradeSupplierWithdrawalAction from '@/components/direct-trade/DirectTradeSupplierWithdrawalAction.vue'
import { navigateTo as nav } from '@/utils/nav'
import { useI18nStore } from '@/store/i18n'
import { useCommerceStore } from '@/store/commerce'
import { localizeProductName } from '@/utils/localize-content'

const i18n = useI18nStore()
const { t, tr } = i18n
const commerce = useCommerceStore()
const wallet = ref<Awaited<ReturnType<typeof getSupplierWallet>> | null>(null)
const records = ref<Awaited<ReturnType<typeof getRevenueDetail>>>([])
const loadError = ref(false)

async function load() {
  loadError.value = false
  const [walletResult, recordsResult] = await Promise.allSettled([getSupplierWallet(), getRevenueDetail()])
  wallet.value = walletResult.status === 'fulfilled' ? walletResult.value : null
  records.value = recordsResult.status === 'fulfilled' ? recordsResult.value : []
  loadError.value = walletResult.status === 'rejected' || recordsResult.status === 'rejected'
}
onShow(() => load())

function goDevices() { nav('/pages/supplier/devices') }
function settlementText(settlementStatus: string, orderStatus: string) {
  if (settlementStatus === 'settled') return t('已结算')
  if (settlementStatus === 'historical_unreconciled') return t('待财务核账')
  if (orderStatus === 'paid') return t('待交付')
  if (orderStatus === 'disputed') return t('争议处理中')
  return t('待确认')
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--card-border); }
.hero { padding: 40rpx 32rpx; margin: 24rpx 0; background: var(--card); border: none; }
.hero-main { margin-bottom: 24rpx; }
.hl { color: var(--text-sub); font-size: 24rpx; }
.hv { display: block; color: var(--text); font-size: 56rpx; font-weight: 800; margin-top: 8rpx; font-variant-numeric: tabular-nums; }
.up { color: var(--up); }
.hero-grid { display: flex; gap: 16rpx; }
.hg-item { flex: 1; text-align: center; background: rgba(255,255,255,0.3); border-radius: 12rpx; padding: 16rpx 0; }
.hg-l { color: var(--text-sub); font-size: 20rpx; display: block; }
.hg-v { color: var(--text); font-size: 26rpx; font-weight: 700; display: block; margin-top: 4rpx; font-variant-numeric: tabular-nums; }
.quick-row { display: flex; gap: 16rpx; margin-bottom: 24rpx; }
.q-btn { flex: 1; text-align: center; padding: 24rpx 0; border-radius: var(--radius); font-size: 28rpx; font-weight: 600; background: linear-gradient(135deg, var(--primary), var(--primary)); color: #fff; }
.q-btn.disabled { opacity: 0.45; }
.q-btn.ghost { background: var(--bg-2); color: var(--text); border: 1rpx solid var(--border); }
.ph { padding: 60rpx 0; }
.rrow { display: flex; justify-content: space-between; align-items: flex-start; padding: 28rpx 32rpx; margin-bottom: 16rpx; gap: 16rpx; }
.rn { color: var(--text); font-size: 28rpx; font-weight: 600; display: block; }
.rg { color: var(--text-sub); font-size: 22rpx; margin-top: 8rpx; display: block; }
.rtags { display: flex; gap: 8rpx; margin-top: 8rpx; }
.rtag { font-size: 20rpx; padding: 4rpx 12rpx; border-radius: 8rpx; background: var(--primary-soft); color: var(--primary); }
.rtag.status.settled { background: var(--up-soft); color: var(--up); }
.rtag.status.pending { background: var(--down-soft); color: var(--down); }
.rtag.status.historical_unreconciled { background: var(--bg-2); color: var(--text-sub); }
.rr { text-align: right; flex-shrink: 0; }
.rv { font-size: 32rpx; font-weight: 700; font-variant-numeric: tabular-nums; display: block; }
.rs { color: var(--text-dim); font-size: 20rpx; margin-top: 4rpx; display: block; }
.ph { color: var(--text-dim); }
.load-error { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; padding: 20rpx 24rpx; margin-bottom: 20rpx; color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); font-size: 23rpx; line-height: 1.5; }
.load-retry { flex-shrink: 0; color: var(--primary); font-weight: 700; min-height: 64rpx; display: flex; align-items: center; }
.audit-note { margin: -8rpx 0 24rpx; padding: 20rpx 24rpx; color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); font-size: 23rpx; line-height: 1.6; }

</style>
