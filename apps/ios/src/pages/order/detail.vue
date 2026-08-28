<template>
  <view class="page">
    <AppNavBar :title="t('k_8054f719')" />
    <scroll-view scroll-y class="body">
      <view v-if="loading" class="state">{{ t('loading') }}</view>
      <view v-else-if="!order" class="state">
        <EmptyState text="订单不存在">
          <AppIcon name="order" :size="56" />
        </EmptyState>
      </view>
      <template v-else>
        <view v-if="order.revenue_settlement_enabled === false" class="service-warning">{{ t('revenueSettlementUnavailable') }}</view>
        <view class="card hero">
          <view class="hero-top">
            <view class="hero-name-wrap">
              <text class="hero-name">{{ localizeProductName(order.product_name || t('算力订单'), i18n.lang) }}</text>
              <text class="hero-no">{{ t('orderNo') }} {{ order.order_no || ('#' + order.id) }}</text>
            </view>
            <StatusBadge :text="badge.text" :type="badge.type" />
          </view>
          <view class="hero-amount">
            <text class="hero-label">{{ t('k_cc6be3d9') }}</text>
            <AmountText :value="order.amount_card_hours ?? order.amount" :prefix="t('cardHour')" size="lg" />
          </view>
        </view>

        <SectionHeader :title="t('k_a6d10d5a')" />
        <view class="card info-card">
          <view class="row"><text class="sk">{{ t('k_21c8bb00') }}</text><text class="sv">{{ order.purchase_type === 'holding' ? t('holdingMode') : order.purchase_type === 'usage' ? t('usageMode') : order.purchase_type || '-' }}</text></view>
          <view class="row"><text class="sk">{{ t('k_0292a021') }}</text><text class="sv">{{ order.end_at ? `${formatDate(order.start_at)} ~ ${formatDate(order.end_at)}` : t('startsAfterDeliveryConfirmation') }}</text></view>
          <view class="row"><text class="sk">{{ t('purchaseDuration') }}</text><text class="sv">{{ orderDuration }}</text></view>
          <view class="row"><text class="sk">{{ t('purchaseQuantity') }}</text><text class="sv">{{ t('quantityUnits', { count: order.quantity || 1 }) }}</text></view>
          <view v-if="order.end_at" class="row"><text class="sk">{{ t('k_927babb3') }}</text><text class="sv">{{ orderRemaining }}</text></view>
          <view class="row" v-if="order.purchase_type !== 'holding' && order.revenue_settlement_enabled"><text class="sk">{{ t('cumulativeRevenue') }}</text><text class="sv up">{{ fmtCH(order.accumulated_revenue ?? 0) }}</text></view>
          <view class="row"><text class="sk">{{ t('gpuModel') }}</text><text class="sv">{{ order.gpu_model || '-' }}</text></view>
          <view v-if="order.status === 'paid' && order.delivery_due_at" class="row"><text class="sk">{{ t('交付截止时间') }}</text><text class="sv">{{ formatDeadline(order.delivery_due_at) }}</text></view>
          <view v-if="order.status === 'delivering' && order.confirmation_due_at" class="row"><text class="sk">{{ t('验收截止时间') }}</text><text class="sv">{{ formatDeadline(order.confirmation_due_at) }}</text></view>
          <view v-if="order.status === 'disputed' && order.dispute_due_at" class="row"><text class="sk">{{ t('争议处理截止时间') }}</text><text class="sv">{{ formatDeadline(order.dispute_due_at) }}</text></view>
        </view>

        <view v-if="order.status === 'disputed'" class="card dispute-card">
          <text class="dispute-title">{{ t('订单正在争议处理中') }}</text>
          <text class="dispute-desc">{{ t('争议期间卡时继续冻结，不会释放给商家；平台逾期未处理将自动退款。') }}</text>
          <text v-if="order.dispute_reason" class="dispute-reason">{{ order.dispute_reason }}</text>
        </view>

        <!-- SSH交付信息（使用模式） -->
        <SectionHeader v-if="order.ssh_info" :title="t('SSH连接信息')" />
        <view v-if="order.ssh_info" class="card ssh-card">
          <text class="ssh-text">{{ order.ssh_info }}</text>
          <view class="ssh-copy" @tap="copySSH"><text class="copy-text">{{ t('k_79d3abe9') }}</text></view>
        </view>

        <SectionHeader v-if="order.asset_id" :title="t('k_5b927139')" />
        <view v-if="order.asset_id" class="card link-card" @tap="goAsset">
          <view class="lc-left">
            <text class="lc-label">{{ t('k_1b683021') }}</text>
            <text class="lc-no">#{{ order.asset_id }}</text>
          </view>
          <AppIcon name="chevron" :size="36" />
        </view>
      </template>
    </scroll-view>

    <BottomActionBar v-if="order">
      <view v-if="order.status === 'delivering'" class="bar-row">
        <view v-if="canDisputeOrder" class="btn ghost" @tap="showDispute = true">{{ t('发起争议') }}</view>
        <view v-if="canConfirmOrder" class="btn primary" @tap="onConfirm">{{ t('确认交付') }}</view>
      </view>
      <view v-else-if="order.status === 'paid'" class="bar-row">
        <view class="info-text">{{ t('waitingForValidSshDelivery') }}</view>
        <view v-if="canCancelOrder" class="btn ghost cancel-pending" @tap="showCancel = true">{{ t('取消订单') }}</view>
      </view>
      <view v-else-if="canRenew" class="bar-row">
        <DirectTradeOrderRenewAction v-if="commerce.directTradeEnabled" :order-id="oid" @refreshed="fetchOrder" />
        <view v-else-if="commerce.matchmakingEnabled" class="btn primary full" @tap="submitRenewalRequirement">{{ t('submitRequirement') }}</view>
        <view v-else class="info-text">{{ t('dataUnavailable') }}</view>
      </view>
      <view v-else-if="order.status === 'completed' && order.purchase_type === 'holding'" class="bar-row">
        <view class="info-text">{{ t('holdingSaleUnavailableNotice') }}</view>
      </view>
      <view v-else-if="order.status === 'disputed'" class="bar-row">
        <view class="info-text">{{ t('等待平台处理争议') }}</view>
      </view>
    </BottomActionBar>

    <ConfirmSheet
      :visible="showCancel"
      :title="t('取消订单')"
      :desc="t('取消后订单将停止计费且无法恢复，确认操作？')"
      :cancelText="t('再想想')"
      :confirmText="t('确认取消')"
      @cancel="showCancel = false"
      @confirm="onCancel"
    />

    <ConfirmSheet
      :visible="showDispute"
      :title="t('发起争议')"
      :desc="t('请说明 SSH 无法连接、配置不符或其他交付问题。提交后卡时保持冻结。')"
      :cancelText="t('取消')"
      :confirmText="t('提交争议')"
      @cancel="showDispute = false"
      @confirm="onDispute"
    >
      <textarea v-model="disputeReason" class="dispute-input" :placeholder="t('至少填写 5 个字的问题说明')" maxlength="500" />
    </ConfirmSheet>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { request } from '@/api/request'
import { getOrder, cancelOrder, disputeOrder, type OrderItem } from '@/api/order'
import { formatDate, formatDeadline, fmtCH } from '@/utils/format'
import AppNavBar from '@/components/AppNavBar.vue'
import AmountText from '@/components/AmountText.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import BottomActionBar from '@/components/BottomActionBar.vue'
import ConfirmSheet from '@/components/ConfirmSheet.vue'
import EmptyState from '@/components/EmptyState.vue'
import AppIcon from '@/components/AppIcon.vue'
import DirectTradeOrderRenewAction from '@/components/direct-trade/DirectTradeOrderRenewAction.vue'
import { navigateTo as nav } from '@/utils/nav'
import { useI18nStore } from '@/store/i18n'
import { useCommerceStore } from '@/store/commerce'
import { localizeProductName } from '@/utils/localize-content'
import { saveInquiryRequestPrefill } from '@/utils/inquiry-request'

const i18n = useI18nStore()
const { t } = i18n
const commerce = useCommerceStore()
const order = ref<OrderItem | null>(null)
const loading = ref(true)
const oid = ref(0)

const showCancel = ref(false)
const showDispute = ref(false)
const disputeReason = ref('')
const submitting = ref(false)

onLoad(async (opts) => {
  oid.value = Number(opts?.id || 0)
  if (!oid.value) {
    loading.value = false
    return
  }
  await fetchOrder()
})

async function fetchOrder() {
  loading.value = true
  try {
    order.value = await getOrder(oid.value)
  } catch {
    /* request 已 toast */
  }
  loading.value = false
}

const badge = computed(() => {
  const s = order.value?.status
  if (s === 'paid') return { text: '待交付', type: 'running' as const }
  if (s === 'delivering') return { text: '待确认', type: 'running' as const }
  if (s === 'running') return { text: '运行中', type: 'running' as const }
  if (s === 'completed') return { text: '已完成', type: 'done' as const }
  if (s === 'disputed') return { text: t('争议处理中'), type: 'running' as const }
  if (s === 'done') return { text: t('已到期'), type: 'expired' as const }
  if (s === 'canceled') return { text: '已取消', type: 'canceled' as const }
  if (s === 'expired') return { text: '已到期', type: 'expired' as const }
  return { text: s || '待处理', type: 'default' as const }
})
const isHourlyOrder = computed(() => order.value?.purchase_unit === 'hour' || Number(order.value?.duration_hours ?? order.value?.purchase_hours) > 0)
const canCancelOrder = computed(() => Boolean(order.value && (order.value.can_cancel ?? order.value.status === 'paid')))
const canConfirmOrder = computed(() => Boolean(order.value && (order.value.can_confirm ?? order.value.status === 'delivering')))
const canDisputeOrder = computed(() => Boolean(order.value && (order.value.can_dispute ?? order.value.status === 'delivering')))
const canRenew = computed(() => order.value?.can_renew === true)
const orderDuration = computed(() => {
  if (!order.value) return '-'
  if (isHourlyOrder.value) return t('hoursValue', { count: Number(order.value.duration_hours ?? order.value.purchase_hours ?? 0) })
  return t('{days} 天', { days: Number(order.value.cycle_days || 0) })
})
const orderRemaining = computed(() => {
  if (!order.value) return '-'
  if (isHourlyOrder.value && order.value.remaining_hours != null) return t('hoursValue', { count: order.value.remaining_hours })
  return t('{days} 天', { days: order.value.remaining_days ?? 0 })
})

function copySSH() {
  if (order.value?.ssh_info) {
    uni.setClipboardData({ data: order.value.ssh_info })
  }
}

async function onConfirm() {
  if (submitting.value || !canConfirmOrder.value) return
  uni.showModal({
    title: t('确认交付'),
    content: t('确认收到商家提供的SSH连接信息，释放冻结资金给商家？'),
    success: async (r) => {
      if (!r.confirm || submitting.value || !canConfirmOrder.value) return
      submitting.value = true
      try {
        await request({ url: `/orders/${oid.value}/confirm`, method: 'POST' })
        uni.showToast({ title: t('确认成功'), icon: 'success' })
        await fetchOrder()
      } catch {
        /* request 已 toast */
      } finally {
        submitting.value = false
      }
    },
  })
}

async function onCancel() {
  showCancel.value = false
  if (submitting.value || !canCancelOrder.value) return
  submitting.value = true
  try {
    await cancelOrder(oid.value)
    uni.showToast({ title: t('已取消'), icon: 'success' })
    await fetchOrder()
  } catch {
    /* request 已 toast */
  } finally {
    submitting.value = false
  }
}

async function onDispute() {
  const reason = disputeReason.value.trim()
  if (reason.length < 5) {
    uni.showToast({ title: t('至少填写 5 个字的问题说明'), icon: 'none' })
    return
  }
  if (submitting.value || !canDisputeOrder.value) return
  submitting.value = true
  try {
    await disputeOrder(oid.value, reason)
    showDispute.value = false
    disputeReason.value = ''
    uni.showToast({ title: t('争议已提交'), icon: 'success' })
    await fetchOrder()
  } catch {
    /* request 已 toast */
  } finally {
    submitting.value = false
  }
}

function submitRenewalRequirement() {
  const current = order.value
  if (!current?.product_id) return
  saveInquiryRequestPrefill({
    product_id: current.product_id,
    supplier_id: current.supplier_id,
    seller_name: current.seller_name || current.supplier_name || '',
    source: current.market_source || current.seller_type || '',
    gpu_model: current.gpu_model || current.product_name || '',
    quantity: Math.max(1, Number(current.quantity) || 1),
    gpu_hours: Math.max(1, Number(current.duration_hours ?? current.purchase_hours) || 24),
    product_name: current.product_name || '',
  })
  nav('/pages/buy-request/index?new=1')
}

function goAsset() {
  const aid = order.value?.asset_id
  if (!aid) return
  nav(`/pages/asset/detail?id=${aid}`)
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.body { flex: 1; padding: 0 32rpx 200rpx; }
.state { color: var(--text-sub); text-align: center; padding: 120rpx 0; font-size: 28rpx; }
.card { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }
.service-warning { color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); padding: 24rpx; margin-bottom: 20rpx; font-size: 24rpx; line-height: 1.6; }

.hero { padding: 36rpx 32rpx; }
.hero-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 16rpx; }
.hero-name-wrap { flex: 1; min-width: 0; }
.hero-name { color: var(--text); font-size: 40rpx; font-weight: 700; display: block; }
.hero-no { color: var(--text-dim); font-size: 24rpx; margin-top: 8rpx; display: block; font-variant-numeric: tabular-nums; }
.hero-amount { display: flex; align-items: baseline; gap: 20rpx; margin-top: 32rpx; }
.hero-label { color: var(--text-sub); font-size: 26rpx; }

.info-card { padding: 4rpx 32rpx; }
.row { display: flex; justify-content: space-between; align-items: center; padding: 28rpx 0; border-bottom: 1rpx solid var(--divider); gap: 24rpx; }
.row:last-child { border-bottom: none; }
.sk { color: var(--text-sub); font-size: 28rpx; flex-shrink: 0; }
.sv { color: var(--text); font-size: 28rpx; font-variant-numeric: tabular-nums; text-align: right; }
.sv.up { color: var(--up); }

.link-card { display: flex; align-items: center; justify-content: space-between; padding: 28rpx 32rpx; color: var(--text-sub); }
.lc-left { display: flex; flex-direction: column; gap: 8rpx; }
.lc-label { color: var(--text-sub); font-size: 24rpx; }
.lc-no { color: var(--text); font-size: 30rpx; font-weight: 600; font-variant-numeric: tabular-nums; }

.bar-row { display: flex; gap: 20rpx; }
.btn { flex: 1; text-align: center; padding: 28rpx 0; border-radius: var(--radius); font-size: 30rpx; }
.btn.ghost { background: var(--bg-2); color: var(--text-sub); }
.btn.primary { background: var(--primary); color: #fff; font-weight: 600; }

.cycles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14rpx; }
.cycle { min-width: 0; text-align: center; padding: 22rpx 4rpx; border: 1rpx solid var(--border); border-radius: 12rpx; color: var(--text-sub); font-size: 23rpx; background: var(--card); }
.cycle.active { border-color: var(--primary); color: var(--primary); background: var(--primary-soft); }

.ssh-card { padding: 28rpx 32rpx; margin-bottom: 24rpx; display: flex; align-items: center; justify-content: space-between; gap: 16rpx; }
.ssh-text { color: var(--text); font-size: 26rpx; flex: 1; line-height: 1.6; word-break: break-all; }
.ssh-copy { flex-shrink: 0; background: var(--primary-soft); color: var(--primary); padding: 12rpx 28rpx; border-radius: var(--radius); font-size: 24rpx; }
.copy-text { color: var(--primary); }
.btn.primary.full { flex: 1; }
.info-text { flex: 1; text-align: center; color: var(--text-sub); font-size: 26rpx; padding: 28rpx 0; }
.dispute-card { margin-top: 24rpx; padding: 28rpx 32rpx; }
.dispute-title { display: block; color: var(--text); font-size: 28rpx; font-weight: 700; }
.dispute-desc { display: block; margin-top: 10rpx; color: var(--text-sub); font-size: 24rpx; line-height: 1.6; }
.dispute-reason { display: block; margin-top: 18rpx; padding: 18rpx; color: var(--text); background: var(--bg-2); border-radius: 12rpx; font-size: 24rpx; line-height: 1.6; }
.dispute-input { box-sizing: border-box; width: 100%; min-height: 180rpx; padding: 20rpx; color: var(--text); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: 12rpx; font-size: 26rpx; line-height: 1.6; }
</style>
