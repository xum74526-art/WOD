<template>
  <view class="page">
    <AppNavBar :title="t('coupons')" />
    <view class="shell">
      <view class="seg-wrap"><SegmentedControl :items="['可用', '已使用', '已过期']" :model-value="tab" @update:model-value="onTab" /></view>
      <view class="redeem-row">
        <input class="rinput" v-model="code" :placeholder="t('k_02ad5a5c')" placeholder-class="ph" />
        <view class="rbtn" @tap="onRedeem">{{ t('k_774e1765') }}</view>
      </view>
      <view v-if="loading && !list.length" class="load-state">{{ t('loading') }}</view>
      <view v-else-if="loadError && !list.length" class="load-state load-error">
        <text>{{ t('dataUnavailable') }}</text>
        <view class="load-retry" role="button" @tap="load">{{ t('retry') }}</view>
      </view>
      <view v-else-if="!list.length" class="card ph"><EmptyState text="暂无优惠券" /></view>
      <view v-for="c in list" :key="c.id" class="card crow">
        <view class="cl"><text class="camount">{{ fmtCH(c.amount) }}</text><text class="cmin">{{ t('满 {amount} 可用', { amount: fmtCH(c.min_amount) }) }}</text></view>
        <view class="cr"><text class="cname">{{ tr(c.name) }}</text><text class="cexp">{{ formatDate(c.expires_at) }} {{ t('到期') }}</text></view>
      </view>
      <view class="tip">{{ t('k_752836ae') }}</view>
    </view>
  </view>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getCoupons, redeemCoupon, type CouponItem } from '@/api/coupon'
import { formatDate, fmtCH } from '@/utils/format'
import AppNavBar from '@/components/AppNavBar.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import EmptyState from '@/components/EmptyState.vue'
import { useI18nStore } from '@/store/i18n'

const { t, tr } = useI18nStore()
const list = ref<CouponItem[]>([])
const loading = ref(true)
const loadError = ref(false)
const tab = ref(0)
const code = ref('')
const STATUS = ['available', 'used', 'expired']

async function load() {
  loading.value = true
  loadError.value = false
  try { list.value = await getCoupons(STATUS[tab.value]) }
  catch { loadError.value = true }
  finally { loading.value = false }
}
onShow(() => load())
function onTab(v: number) { tab.value = v; load() }
async function onRedeem() {
  if (!code.value) { uni.showToast({ title: t('请输入兑换码'), icon: 'none' }); return }
  try { await redeemCoupon(code.value); uni.showToast({ title: t('兑换成功'), icon: 'success' }); code.value = ''; await load() } catch {}
}
</script>
<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.seg-wrap { margin: 16rpx 0 24rpx; }
.redeem-row { display: flex; gap: 16rpx; margin-bottom: 24rpx; }
.rinput { flex: 1; background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); padding: 24rpx; color: var(--text); font-size: 28rpx; }
.ph { color: var(--text-dim); }
.rbtn { background: var(--primary); color: #fff; padding: 24rpx 40rpx; border-radius: var(--radius); font-size: 28rpx; font-weight: 600; }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--border); }
.load-state { min-height: 180rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 26rpx; }
.load-error { flex-direction: column; gap: 18rpx; }
.load-retry { min-height: 68rpx; padding: 0 28rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: var(--radius); font-weight: 700; }
.ph { padding: 60rpx 0; }
.crow { display: flex; align-items: center; padding: 32rpx; margin-bottom: 16rpx; background: linear-gradient(135deg, var(--card-border), rgba(13,148,168,0.02)); }
.cl { width: 200rpx; text-align: center; border-right: 1rpx dashed var(--border); }
.camount { display: block; color: var(--primary); font-size: 52rpx; font-weight: 800; }
.cmin { display: block; color: var(--text-sub); font-size: 22rpx; margin-top: 8rpx; }
.cr { flex: 1; padding-left: 32rpx; }
.cname { display: block; color: var(--text); font-size: 28rpx; font-weight: 600; }
.cexp { display: block; color: var(--text-dim); font-size: 22rpx; margin-top: 8rpx; }
.tip { color: var(--text-dim); font-size: 22rpx; text-align: center; margin-top: 24rpx; }
</style>
