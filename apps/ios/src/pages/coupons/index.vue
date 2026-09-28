<template>
  <view class="page">
    <AppNavBar :title="t('coupons')" />
    <view class="shell">
      <view class="card redeem-card">
        <view class="redeem-copy">
          <text class="redeem-title">{{ t('couponRedeemTitle') }}</text>
          <text class="redeem-hint">{{ t('couponRedeemHint') }}</text>
        </view>
        <view class="redeem-form">
          <input v-model="redeemCode" class="redeem-input" :placeholder="t('couponCodePlaceholder')" maxlength="48" confirm-type="done" @confirm="submitRedeem" />
          <view class="redeem-button" :class="{ disabled: redeeming || !redeemCode.trim() }" role="button" @tap="submitRedeem">
            {{ t(redeeming ? 'couponRedeeming' : 'couponRedeem') }}
          </view>
        </view>
      </view>
      <view class="seg-wrap">
        <SegmentedControl :items="tabLabels" :model-value="tab" @update:model-value="onTab" />
      </view>
      <view v-if="loading && !list.length" class="coupon-stack" :aria-label="t('loading')">
        <view v-for="index in 2" :key="index" class="card coupon-skeleton">
          <view class="skeleton-value" />
          <view class="skeleton-copy">
            <view class="skeleton-line wide" />
            <view class="skeleton-line" />
          </view>
        </view>
      </view>
      <view v-else-if="loadError && !list.length" class="card load-state load-error">
        <text class="error-title">{{ t('couponLoadFailed') }}</text>
        <text class="error-detail">{{ loadError }}</text>
        <view class="load-retry" role="button" :aria-label="t('retry')" @tap="load">{{ t('retry') }}</view>
      </view>
      <view v-else-if="!list.length" class="card empty-card">
        <EmptyState :text="emptyText" />
      </view>
      <view v-else class="coupon-stack">
        <view v-for="coupon in list" :key="coupon.id" class="card coupon-row">
          <view class="coupon-value">
            <view class="amount-line">
              <text class="coupon-amount">{{ fmtCardHours(coupon.amount) }}</text>
              <text class="coupon-unit">{{ t('cardHour') }}</text>
            </view>
            <text class="coupon-min">{{ t('couponMinimum', { amount: fmtCardHours(coupon.min_amount) }) }}</text>
          </view>
          <view class="coupon-copy">
            <view class="coupon-heading">
              <text class="coupon-name">{{ tr(coupon.name) }}</text>
              <text class="coupon-status" :class="`status-${coupon.status}`">{{ statusText(coupon.status) }}</text>
            </view>
            <text class="coupon-date">{{ couponDateText(coupon) }}</text>
          </view>
        </view>
      </view>
      <view class="tip">{{ t('couponIssuedHint') }}</view>
    </view>
  </view>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getCoupons, redeemCoupon, type CouponItem, type CouponStatus } from '@/api/coupon'
import { formatDate, fmtCardHours } from '@/utils/format'
import AppNavBar from '@/components/AppNavBar.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import EmptyState from '@/components/EmptyState.vue'
import { useI18nStore } from '@/store/i18n'

const { t, tr, localizedErrorMessage } = useI18nStore()
const list = ref<CouponItem[]>([])
const loading = ref(true)
const loadError = ref('')
const tab = ref(0)
const redeemCode = ref('')
const redeeming = ref(false)
const STATUS: CouponStatus[] = ['available', 'used', 'expired']
const tabLabels = computed(() => [t('couponAvailable'), t('couponUsed'), t('couponExpired')])
const emptyText = computed(() => [
  t('couponEmptyAvailable'),
  t('couponEmptyUsed'),
  t('couponEmptyExpired'),
][tab.value])

function couponError(error: unknown, fallback: string) {
  return localizedErrorMessage(error, fallback)
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    list.value = await getCoupons(STATUS[tab.value])
  } catch (error) {
    list.value = []
    loadError.value = couponError(error, 'couponLoadFailedHint')
  }
  finally { loading.value = false }
}
onShow(() => load())
function onTab(v: number) { tab.value = v; load() }

async function submitRedeem() {
  const code = redeemCode.value.trim()
  if (!code || redeeming.value) return
  redeeming.value = true
  try {
    await redeemCoupon(code)
    redeemCode.value = ''
    tab.value = 0
    await load()
    uni.showToast({ title: t('couponRedeemSuccess'), icon: 'success' })
  } catch (error) {
    uni.showToast({ title: couponError(error, 'couponRedeemFailed'), icon: 'none' })
  } finally {
    redeeming.value = false
  }
}

function statusText(status: CouponStatus) {
  return t(status === 'available' ? 'couponAvailable' : status === 'used' ? 'couponUsed' : 'couponExpired')
}

function couponDateText(coupon: CouponItem) {
  if (coupon.status === 'used') return t('couponUsedHint')
  const date = formatDate(coupon.expires_at || undefined)
  if (!date) return t(coupon.status === 'expired' ? 'couponExpiredHint' : 'couponNoExpiry')
  return t(coupon.status === 'expired' ? 'couponExpiredOn' : 'couponExpiresOn', { date })
}
</script>
<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.seg-wrap { margin: 16rpx 0 24rpx; }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--border); }
.redeem-card { margin: 16rpx 0 24rpx; padding: 26rpx; }
.redeem-copy { display: flex; flex-direction: column; gap: 6rpx; }
.redeem-title { color: var(--text); font-size: 27rpx; font-weight: 800; }
.redeem-hint { color: var(--text-sub); font-size: 21rpx; line-height: 1.5; }
.redeem-form { display: flex; align-items: center; gap: 14rpx; margin-top: 20rpx; }
.redeem-input { min-width: 0; flex: 1; height: 76rpx; padding: 0 22rpx; color: var(--text); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: 14rpx; font-size: 24rpx; }
.redeem-button { min-width: 132rpx; height: 76rpx; padding: 0 20rpx; display: flex; align-items: center; justify-content: center; color: #fff; background: var(--primary); border-radius: 14rpx; font-size: 24rpx; font-weight: 700; }
.redeem-button.disabled { opacity: .45; }
.coupon-stack { display: flex; flex-direction: column; gap: 16rpx; }
.load-state { min-height: 300rpx; padding: 44rpx 32rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 26rpx; }
.load-error { flex-direction: column; gap: 14rpx; text-align: center; }
.error-title { color: var(--text); font-weight: 700; }
.error-detail { color: var(--text-sub); font-size: 23rpx; line-height: 1.55; }
.load-retry { min-height: 72rpx; margin-top: 4rpx; padding: 0 32rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: var(--radius); font-weight: 700; }
.load-retry:active { transform: translateY(1rpx); }
.empty-card { overflow: hidden; }
.coupon-row { min-height: 188rpx; display: flex; align-items: stretch; overflow: hidden; }
.coupon-value { width: 224rpx; padding: 30rpx 20rpx; display: flex; flex-direction: column; align-items: center; justify-content: center; background: var(--primary-soft); border-right: 1rpx dashed var(--border); text-align: center; }
.amount-line { display: flex; align-items: baseline; justify-content: center; max-width: 100%; }
.coupon-amount { color: var(--primary); font-size: 48rpx; font-weight: 800; font-variant-numeric: tabular-nums; }
.coupon-unit { margin-left: 5rpx; color: var(--primary); font-size: 21rpx; font-weight: 700; }
.coupon-min { margin-top: 8rpx; color: var(--text-sub); font-size: 20rpx; line-height: 1.4; }
.coupon-copy { min-width: 0; flex: 1; padding: 30rpx 26rpx; display: flex; flex-direction: column; justify-content: center; }
.coupon-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12rpx; }
.coupon-name { min-width: 0; flex: 1; color: var(--text); font-size: 27rpx; font-weight: 700; line-height: 1.4; }
.coupon-status { flex-shrink: 0; padding: 5rpx 10rpx; border-radius: 10rpx; color: var(--text-sub); background: var(--bg-2); font-size: 19rpx; }
.coupon-status.status-available { color: var(--primary); background: var(--primary-soft); }
.coupon-date { display: block; margin-top: 14rpx; color: var(--text-dim); font-size: 22rpx; line-height: 1.5; }
.tip { color: var(--text-dim); font-size: 22rpx; line-height: 1.6; text-align: center; margin: 28rpx 18rpx 0; }
.coupon-skeleton { min-height: 188rpx; display: flex; align-items: center; padding: 28rpx; }
.skeleton-value { width: 166rpx; height: 92rpx; border-radius: 14rpx; background: var(--bg-2); }
.skeleton-copy { flex: 1; padding-left: 28rpx; }
.skeleton-line { width: 62%; height: 22rpx; margin-top: 18rpx; border-radius: 8rpx; background: var(--bg-2); }
.skeleton-line.wide { width: 88%; margin-top: 0; height: 28rpx; }
@media (prefers-reduced-motion: no-preference) {
  .coupon-skeleton { animation: coupon-pulse 1.4s ease-in-out infinite alternate; }
}
@keyframes coupon-pulse { from { opacity: .58; } to { opacity: 1; } }
</style>
