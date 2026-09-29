<template>
  <view :class="['page', pageMotionClass]">
    <view class="shell" :style="{ paddingTop: 'calc(28rpx + var(--safe-top))' }">
      <view class="role-bar" v-if="canSwitchRole">
        <text class="role-text">{{ t('currentMode') }}{{ t(role === 'personal' ? 'personalMode' : 'supplierMode') }}</text>
        <text class="role-switch" @tap="onSwitchRole">{{ t(role === 'personal' ? '切换为商家 ›' : '切换回个人 ›') }}</text>
      </view>
      <view v-if="loadError" class="load-error">
        <text>{{ t('profileLoadFailedDesc') }}</text>
        <text class="load-retry" @tap="load">{{ t('retry') }}</text>
      </view>
      <view class="user-card pressable" @tap="goProfile">
        <view class="avatar">
          <image v-if="avatarUrl" class="avatar-img" :src="avatarUrl" mode="aspectFill" @error="avatarLoadFailed = true" />
          <text v-else>{{ avatarText }}</text>
        </view>
        <view class="uinfo">
          <text class="uname">{{ displayUsername }}</text>
          <text class="uphone">{{ user?.phone || '' }}</text>
        </view>
        <view class="uarrow"><AppIcon name="chevron" :size="36" /></view>
      </view>

      <!-- 个人模式：总资产 + 邀请好友 -->
      <view class="top-row" v-if="role === 'personal'">
        <view class="card summary pressable" @tap="goAssets">
          <text class="sum-label">{{ t("totalAssets") }}</text>
          <AmountText :value="totalAsset" currency="ledger" size="lg" />
          <view class="sum-mini">
            <text class="sm-l">{{ t("wallet") }}</text>
            <text class="sm-v">{{ formatCardHourCurrency(wallet?.balance) }}</text>
          </view>
        </view>
        <view class="card invite-card pressable" @tap="goInvite">
          <view class="iv-icons"><AppIcon name="coin" :size="36" /><AppIcon name="friends" :size="36" /></view>
          <text class="iv-label">{{ t("inviteFriends") }}</text>
          <text class="iv-val">{{ invite?.invited_count || 0 }} {{ t('people') }}</text>
          <text v-if="invite?.rewards_enabled" class="iv-reward">{{ t('reward') }} {{ formatCardHourCurrency(invite?.total_reward || 0) }}</text>
          <text v-else class="iv-reward muted">{{ t('rewardsUnavailableShort') }}</text>
        </view>
      </view>

      <!-- 商家模式：出租收入 + 设备概览 -->
      <view class="top-row" v-else>
        <view class="card summary pressable" @tap="go('/pages/supplier/revenue')">
          <text class="sum-label">{{ t('k_815f90b8') }}</text>
          <AmountText :value="supplierWallet?.total_revenue ?? 0" currency="ledger" size="lg" />
          <view class="sum-mini">
            <text class="sm-l">{{ t('k_f7e76123') }}</text>
            <text class="sm-v up">{{ formatCardHourCurrency(supplierWallet?.available) }}</text>
          </view>
          <view class="sum-mini" style="margin-top: 8rpx;">
            <text class="sm-l">{{ t('today') }}</text>
            <text class="sm-v">{{ formatCardHourCurrency(supplierWallet?.today_revenue) }}</text>
          </view>
        </view>
        <view class="card invite-card pressable" @tap="go('/pages/supplier/devices')">
          <view class="iv-icons"><AppIcon name="gpu" :size="36" /></view>
          <text class="iv-label">{{ t('merchantResourceManagement') }}</text>
          <text class="iv-val">{{ dash?.product_count ?? 0 }} {{ t('units') }}</text>
          <text class="iv-reward">{{ t('rentable') }} {{ dash?.total_stock ?? 0 }} {{ t('units') }}</text>
        </view>
      </view>

      <!-- 商家销售返佣：按已确认销售金额累计，和购买返佣独立。 -->
      <view v-if="role === 'supplier' && supplierRebate" class="card rebate-card pressable" @tap="go('/pages/supplier/rebate')">
        <view class="rb-title-row">
          <text class="rb-title">{{ t('supplierSalesRebateTitle') }}</text>
          <text v-if="supplierRebate.reward_mode === 'test_card_hours'" class="rb-mode">{{ t('closedTestRewardBadge') }}</text>
        </view>
        <view class="rb-row">
          <view class="rb-item">
            <text class="rb-v up">{{ formatCardHourCurrency(supplierRebate.month_rebated) }}</text>
            <text class="rb-l">{{ t('k_25a91550') }}</text>
          </view>
          <view class="rb-item">
            <text class="rb-v">{{ formatNumber(supplierRebate.current_rate) }}%</text>
            <text class="rb-l">{{ t('k_cfc752a6') }}</text>
          </view>
          <view class="rb-item">
            <text class="rb-v">{{ formatCardHourCurrency(supplierRebate.month_sales) }}</text>
            <text class="rb-l">{{ t('k_e1e32957') }}</text>
          </view>
        </view>
        <text class="rb-hint">{{ tr(supplierRebate.next_tier_hint) }}</text>
        <text class="rb-explain">{{ t('supplierSalesRebateCardHint', { cap: formatCardHourCurrency(supplierRebate.monthly_cap) }) }}</text>
      </view>

      <!-- 个人购买返佣：商家作为买家时同样适用。 -->
      <view v-if="rebate" class="card rebate-card pressable" @tap="go('/pages/rebate/index')">
        <view class="rb-title-row">
          <text class="rb-title">{{ t('personalPurchaseRebateTitle') }}</text>
          <text v-if="rebate.reward_mode === 'test_card_hours'" class="rb-mode">{{ t('closedTestRewardBadge') }}</text>
        </view>
        <view class="rb-row">
          <view class="rb-item">
            <text class="rb-v">{{ formatCardHourCurrency(rebate.month_rebated) }}</text>
            <text class="rb-l">{{ t('k_25a91550') }}</text>
          </view>
          <view class="rb-item">
            <text class="rb-v up">{{ formatNumber(rebate.current_rate) }}%</text>
            <text class="rb-l">{{ t('k_5bfd670e') }}</text>
          </view>
          <view class="rb-item">
            <text class="rb-v">{{ formatCardHourCurrency(rebate.pending_rebate) }}</text>
            <text class="rb-l">{{ t('k_ec4f52f4') }}</text>
          </view>
        </view>
        <text class="rb-hint">{{ tr(rebate.next_tier_hint) }}</text>
        <text class="rb-explain">{{ t('personalPurchaseRebateCardHint', { cap: formatCardHourCurrency(rebate.monthly_cap) }) }}</text>
      </view>

      <view v-for="group in widgetGroups" :key="group.key" class="card widget-card">
        <text class="widget-title">{{ t(group.label) }}</text>
        <view class="grid-card">
          <view v-for="it in group.items" :key="it.key" class="g-item pressable" @tap="onTap(it)">
            <view class="g-icon"><AppIcon :name="it.icon" :size="44" /></view>
            <text class="g-text">{{ t(it.label) }}</text>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { useUserStore } from '@/store/user'
import { useAssetStore } from '@/store/asset'
import { getWallet, type WalletInfo } from '@/api/wallet'
import { getInviteSummary, type InviteSummary } from '@/api/invite'
import { getDashboard, getSupplierWallet, getSupplierRebate, type SupplierRebate } from '@/api/supplier'
import { getRebateSummary, type RebateSummary } from '@/api/user'
import { formatCardHourCurrency, formatNumber } from '@/utils/format'
import { navigateTo as nav, switchTab } from '@/utils/nav'
import AmountText from '@/components/AmountText.vue'
import AppIcon from '@/components/AppIcon.vue'
import { useI18nStore } from '@/store/i18n'
import { localizePersonName } from '@/utils/localize-content'
import { resolveApiMediaUrl } from '@/utils/config'
import { getProfileWidgetGroups, type ProfileWidget } from '@/config/profile-widgets'
import { usePageMotion } from '@/utils/page-motion'

const userStore = useUserStore()
const assetStore = useAssetStore()
const role = computed(() => userStore.role)
const canSwitchRole = computed(() => userStore.canSwitchRole)
const i18n = useI18nStore()
const { t, tr } = i18n
const { pageMotionClass } = usePageMotion()
const wallet = ref<WalletInfo | null>(null)
const invite = ref<InviteSummary | null>(null)
const rebate = ref<RebateSummary | null>(null)
const supplierRebate = ref<SupplierRebate | null>(null)
const dash = ref<Awaited<ReturnType<typeof getDashboard>> | null>(null)
const supplierWallet = ref<Awaited<ReturnType<typeof getSupplierWallet>> | null>(null)
const loadError = ref(false)

const user = computed(() => userStore.userInfo)
const displayUsername = computed(() => localizePersonName(user.value?.username || t('未登录'), i18n.lang))
const avatarText = computed(() => displayUsername.value.slice(0, 1).toUpperCase())
const avatarLoadFailed = ref(false)
const avatarUrl = computed(() => avatarLoadFailed.value ? '' : resolveApiMediaUrl(user.value?.avatar))
const totalAsset = computed(() => (assetStore.summary?.total_value ?? 0) + (wallet.value?.balance ?? 0))

const widgetGroups = computed(() => getProfileWidgetGroups(role.value, canSwitchRole.value))

async function load() {
  loadError.value = false
  if (userStore.role === 'supplier') {
    wallet.value = null
    invite.value = null
    const [dashboardResult, walletResult, supplierRebateResult, personalRebateResult] = await Promise.allSettled([
      getDashboard(), getSupplierWallet(), getSupplierRebate(), getRebateSummary(),
    ])
    dash.value = dashboardResult.status === 'fulfilled' ? dashboardResult.value : null
    supplierWallet.value = walletResult.status === 'fulfilled' ? walletResult.value : null
    supplierRebate.value = supplierRebateResult.status === 'fulfilled' ? supplierRebateResult.value : null
    rebate.value = personalRebateResult.status === 'fulfilled' ? personalRebateResult.value : null
    loadError.value = [dashboardResult, walletResult, supplierRebateResult, personalRebateResult].some((result) => result.status === 'rejected')
  } else {
    dash.value = null
    supplierWallet.value = null
    supplierRebate.value = null
    const [walletResult, inviteResult, rebateResult, assetResult] = await Promise.allSettled([
      getWallet(), getInviteSummary(), getRebateSummary(), assetStore.refresh(),
    ])
    wallet.value = walletResult.status === 'fulfilled' ? walletResult.value : null
    invite.value = inviteResult.status === 'fulfilled' ? inviteResult.value : null
    rebate.value = rebateResult.status === 'fulfilled' ? rebateResult.value : null
    loadError.value = [walletResult, inviteResult, rebateResult, assetResult].some((result) => result.status === 'rejected')
  }
}

onShow(async () => {
  i18n.updateTabBar()
  if (!userStore.isLogin) return
  try { await userStore.fetchProfile() } catch { loadError.value = true }
  avatarLoadFailed.value = false
  load().catch(() => {})
})

function onTap(it: ProfileWidget) {
  nav(it.route)
}

function goAssets() { switchTab('/pages/assets/index') }
function go(url: string) { nav(url) }
function goInvite() { nav('/pages/invite/index') }
function goWallet() { nav('/pages/wallet/index') }
function goRevenue() { nav('/pages/revenue/index') }
function goProfile() { nav('/pages/profile-edit/index') }

async function onSwitchRole() {
  try {
    const newRole = await userStore.switchRole()
    uni.showToast({ title: t('已切换到 {mode}', { mode: t(newRole === 'supplier' ? 'supplierMode' : 'personalMode') }), icon: 'success' })
    if (newRole === 'supplier') {
      nav('/pages/supplier/dashboard')
    } else {
      // 切回个人模式：立即重新加载数据（onShow 不会触发，因为页面未离开）
      load().catch(() => {})
    }
  } catch {}
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }

.role-bar { display: flex; justify-content: space-between; align-items: center; padding: 12rpx 24rpx; margin-bottom: 16rpx; background: linear-gradient(135deg, var(--card-border), rgba(24,175,196,0.04)); border-radius: var(--radius); border: 1rpx solid var(--card-border); }
.role-text { color: var(--text-sub); font-size: 24rpx; }
.role-switch { min-height: 72rpx; display: flex; align-items: center; color: var(--primary); font-size: 26rpx; font-weight: 600; }
.user-card { display: flex; align-items: center; padding: 16rpx 8rpx 32rpx; }
.avatar { width: 96rpx; height: 96rpx; border-radius: 48rpx; background: linear-gradient(135deg, var(--primary), var(--primary)); color: #fff; font-size: 44rpx; font-weight: 700; display: flex; align-items: center; justify-content: center; margin-right: 28rpx; overflow: hidden; flex-shrink: 0; }
.avatar-img { width: 96rpx; height: 96rpx; display: block; }
.uinfo { flex: 1; }
.uname { color: var(--text); font-size: 36rpx; font-weight: 700; display: block; }
.uphone { color: var(--text-sub); font-size: 26rpx; margin-top: 8rpx; display: block; }
.uarrow { color: var(--text-dim); }

.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--border); }
.top-row { display: flex; gap: 16rpx; margin-bottom: 24rpx; }
.summary { flex: 1; padding: 36rpx 28rpx; background: var(--card); border: none; box-shadow: 0 4rpx 24rpx var(--card-border); }
.summary :deep(.amount) { color: var(--text); }
.sum-label { display: block; color: var(--text-sub); font-size: 22rpx; margin-bottom: 8rpx; }
.sum-mini { display: flex; gap: 12rpx; align-items: baseline; margin-top: 16rpx; }
.sm-l { color: var(--text-sub); font-size: 22rpx; }
.sm-v { color: var(--text); font-size: 26rpx; font-weight: 600; font-variant-numeric: tabular-nums; }
.invite-card { flex: 1; padding: 36rpx 28rpx; background: var(--card); border: none; box-shadow: 0 4rpx 24rpx var(--card-border); display: flex; flex-direction: column; align-items: center; justify-content: center; }
.iv-icons { display: flex; gap: 12rpx; margin-bottom: 12rpx; }
.iv-label { color: var(--text-sub); font-size: 22rpx; }
.iv-val { color: var(--text); font-size: 40rpx; font-weight: 800; margin: 8rpx 0; font-variant-numeric: tabular-nums; }
.iv-reward { color: var(--up); font-size: 22rpx; font-weight: 600; }
.iv-reward.muted { color: var(--text-sub); font-weight: 500; text-align: center; }
.load-error { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; padding: 20rpx 24rpx; margin-bottom: 12rpx; color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); font-size: 23rpx; line-height: 1.5; }
.load-retry { flex-shrink: 0; color: var(--primary); font-weight: 700; min-height: 64rpx; display: flex; align-items: center; }

.widget-card { margin-bottom: 20rpx; overflow: hidden; }
.widget-title { display: block; padding: 24rpx 24rpx 8rpx; color: var(--text-sub); font-size: 22rpx; font-weight: 650; }
.grid-card { padding: 4rpx 8rpx 20rpx; display: flex; flex-wrap: wrap; }
.rebate-card { padding: 28rpx 32rpx; margin-bottom: 20rpx; }
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
.rb-explain { display: block; color: var(--text-sub); font-size: 21rpx; line-height: 1.5; margin-top: 12rpx; text-align: center; }
.g-item { width: 25%; display: flex; flex-direction: column; align-items: center; padding: 24rpx 0; color: var(--primary); }
.g-icon { margin-bottom: 14rpx; }
.g-text { color: var(--text); font-size: 24rpx; text-align: center; }
</style>
