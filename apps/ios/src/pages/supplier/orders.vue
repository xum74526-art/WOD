<template>
  <view class="page">
    <AppNavBar :title="t('k_d2523179')" />
    <view class="shell">
      <view class="operation-note">
        <text class="operation-title">{{ t('mobileMerchantDeliveryTitle') }}</text>
        <text class="operation-desc">{{ t('mobileMerchantDeliveryHint') }}</text>
      </view>
      <view class="seg-wrap">
        <SegmentedControl :items="segmentItems" :model-value="tab" @update:model-value="onTab" />
      </view>
      <view v-if="loading" class="state">{{ t("loading") }}</view>
      <view v-else-if="loadError" class="load-error"><text>{{ t('listLoadFailedDesc') }}</text><text class="load-retry" @tap="load">{{ t('retry') }}</text></view>
      <view v-else-if="!list.length" class="card ph"><EmptyState :text="t('暂无订单')" /></view>
      <view v-for="o in list" :key="o.id" class="card orow">
        <view class="ol">
          <view class="ol-row">
            <text class="on">{{ localizeProductName(o.product_name, i18n.lang) }}</text>
            <StatusBadge :text="statusText(o.status)" :type="statusType(o.status)" />
          </view>
          <text class="og">{{ o.order_no }} · {{ o.gpu_model }} × {{ o.quantity || 1 }} · {{ orderAmountText(o) }}</text>
          <text v-if="o.buyer_name || o.buyer_phone" class="buyer-line">{{ t('buyer') }}：{{ o.buyer_name || '-' }}{{ o.buyer_phone ? ` · ${o.buyer_phone}` : '' }}</text>
          <text v-if="deadlineText(o)" class="deadline">{{ deadlineText(o) }}</text>
          <text class="delivery-type">{{ t(o.fulfillment_mode === 'platform_manual' ? 'platformManualSshDelivery' : 'merchantManualSshDelivery') }}</text>
          <text class="os" v-if="o.ssh_info">SSH: {{ o.ssh_info }}</text>
          <text v-if="o.status === 'disputed' && o.dispute_reason" class="dispute-reason">{{ t('disputeReasonLabel') }}：{{ o.dispute_reason }}</text>
        </view>
        <view class="or">
          <view v-if="canDeliver(o)" class="deliver-button" @tap="openDelivery(o)">{{ t('deliverResource') }}</view>
          <text v-else-if="o.status === 'delivering'" class="os-text">{{ t('pendingBuyerAcceptance') }}</text>
          <text v-else-if="o.status === 'disputed'" class="os-text disputed">{{ t('disputeInProgress') }}</text>
        </view>
      </view>
    </view>
    <view v-if="deliveryShow" class="delivery-mask" @tap="closeDelivery">
      <view class="delivery-sheet" @tap.stop>
        <text class="delivery-sheet-title">{{ t('deliverComputeResource') }}</text>
        <text class="delivery-sheet-desc">{{ t('deliverComputeResourceHint', { order: deliveryTarget?.order_no || '-' }) }}</text>
        <textarea
          v-model="sshInfo"
          class="ssh-input"
          :placeholder="t('k_3220447b')"
          maxlength="2000"
          auto-height
        />
        <text class="delivery-security-hint">{{ t('deliverySecurityHint') }}</text>
        <view class="delivery-actions">
          <view class="delivery-cancel" @tap="closeDelivery">{{ t('cancel') }}</view>
          <view class="delivery-submit" :class="{ disabled: delivering }" @tap="submitDelivery">{{ t(delivering ? 'loading' : 'submitDelivery') }}</view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { deliverSupplierOrder, getSupplierOrders, type SupplierOrderItem } from '@/api/supplier'
import AppNavBar from '@/components/AppNavBar.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import EmptyState from '@/components/EmptyState.vue'
import { fmtCardHours, formatDeadline, toCardHours } from '@/utils/format'
import { useI18nStore } from '@/store/i18n'
import { localizeProductName } from '@/utils/localize-content'
import { isValidSshInfo } from '@/utils/ssh-info'

const i18n = useI18nStore()
const { t } = i18n
const list = ref<SupplierOrderItem[]>([])
const loading = ref(true)
const loadError = ref(false)
const tab = ref(0)
const deliveryShow = ref(false)
const deliveryTarget = ref<SupplierOrderItem | null>(null)
const sshInfo = ref('')
const delivering = ref(false)

const STATUS_FILTERS: Array<string | undefined> = ['paid', 'delivering', 'disputed', undefined]
const HISTORY_STATUSES = new Set(['completed', 'running', 'done', 'canceled', 'refunded'])
const segmentItems = computed(() => [t('pendingDelivery'), t('pendingBuyerAcceptance'), t('disputeInProgress'), t('orderHistory')])

async function load() {
  loading.value = true
  loadError.value = false
  list.value = []
  try {
    const rows = await getSupplierOrders(STATUS_FILTERS[tab.value])
    list.value = tab.value === 3 ? rows.filter((order) => HISTORY_STATUSES.has(order.status)) : rows
  } catch { loadError.value = true }
  loading.value = false
}
onShow(() => load())
function onTab(v: number) { tab.value = v; load() }

function statusText(s: string) {
  const m: Record<string, string> = { paid: 'pendingDelivery', delivering: 'pendingBuyerAcceptance', disputed: 'disputeInProgress', completed: 'completed', running: 'statusRunning', done: 'expired', canceled: 'canceled', refunded: 'refunded' }
  return t(m[s] || s)
}
function statusType(s: string): any {
  const m: Record<string, string> = { paid: 'running', delivering: 'running', disputed: 'running', completed: 'done', running: 'running', done: 'expired', canceled: 'canceled', refunded: 'canceled' }
  return m[s] || 'default'
}

function canDeliver(order: SupplierOrderItem) {
  return order.can_deliver ?? order.status === 'paid'
}

function orderAmountText(order: SupplierOrderItem) {
  const value = order.amount_card_hours ?? toCardHours(order.amount)
  return `${fmtCardHours(value)} ${t('cardHour')}`
}

function deadlineText(order: SupplierOrderItem) {
  if (order.status === 'paid' && order.delivery_due_at) return `${t('deliveryDeadline')}：${formatDeadline(order.delivery_due_at)}`
  if (order.status === 'delivering' && order.confirmation_due_at) return `${t('acceptanceDeadline')}：${formatDeadline(order.confirmation_due_at)}`
  if (order.status === 'disputed' && order.dispute_due_at) return `${t('disputeDeadline')}：${formatDeadline(order.dispute_due_at)}`
  return ''
}

function openDelivery(order: SupplierOrderItem) {
  if (delivering.value) return
  deliveryTarget.value = order
  sshInfo.value = ''
  deliveryShow.value = true
}

function closeDelivery() {
  if (delivering.value) return
  deliveryShow.value = false
  deliveryTarget.value = null
  sshInfo.value = ''
}

async function submitDelivery() {
  const target = deliveryTarget.value
  const value = sshInfo.value.trim()
  if (!target || delivering.value) return
  if (!isValidSshInfo(value)) {
    uni.showToast({ title: t('enterValidSshInfo'), icon: 'none' })
    return
  }
  delivering.value = true
  try {
    await deliverSupplierOrder(target.id, value)
    deliveryShow.value = false
    deliveryTarget.value = null
    sshInfo.value = ''
    uni.showToast({ title: t('deliverySubmitted'), icon: 'success' })
    await load()
  } catch (error) {
    uni.showToast({ title: error instanceof Error && error.message ? error.message : t('operationFailed'), icon: 'none' })
  } finally {
    delivering.value = false
  }
}

</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.operation-note { padding: 20rpx 22rpx; margin: 16rpx 0 18rpx; background: var(--primary-soft); border: 1rpx solid rgba(24,175,196,.2); border-radius: var(--radius); }
.operation-title { display: block; color: var(--text); font-size: 24rpx; font-weight: 700; }
.operation-desc { display: block; margin-top: 6rpx; color: var(--text-sub); font-size: 21rpx; line-height: 1.5; }
.seg-wrap { margin: 16rpx 0 24rpx; }
.state { color: var(--text-sub); text-align: center; padding: 60rpx 0; font-size: 26rpx; }
.load-error { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; padding: 20rpx 24rpx; color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); font-size: 23rpx; line-height: 1.5; }
.load-retry { flex-shrink: 0; color: var(--primary); font-weight: 700; min-height: 64rpx; display: flex; align-items: center; }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--card-border); }
.ph { padding: 60rpx 0; }
.orow { display: flex; justify-content: space-between; align-items: flex-start; padding: 32rpx; margin-bottom: 16rpx; gap: 16rpx; }
.ol { flex: 1; }
.ol-row { display: flex; align-items: center; gap: 16rpx; margin-bottom: 12rpx; }
.on { color: var(--text); font-size: 30rpx; font-weight: 600; }
.og { display: block; color: var(--text-sub); font-size: 24rpx; line-height: 1.5; }
.buyer-line, .deadline, .delivery-type { display: block; color: var(--text-sub); font-size: 21rpx; margin-top: 8rpx; line-height: 1.45; }
.delivery-type { color: var(--primary); }
.os { display: block; color: var(--text); font-size: 22rpx; margin-top: 10rpx; padding: 14rpx; background: var(--bg-2); border-radius: 10rpx; line-height: 1.5; word-break: break-all; }
.dispute-reason { display: block; margin-top: 10rpx; color: var(--down); font-size: 21rpx; line-height: 1.5; }
.or { flex-shrink: 0; }
.os-text { color: var(--text-sub); font-size: 24rpx; }
.os-text.disputed { color: var(--down); }
.deliver-button { min-height: 64rpx; display: flex; align-items: center; justify-content: center; padding: 0 22rpx; color: #fff; background: var(--primary); border-radius: 12rpx; font-size: 23rpx; font-weight: 700; }
.delivery-mask { position: fixed; inset: 0; z-index: 50; display: flex; align-items: flex-end; background: rgba(10, 20, 28, .42); }
.delivery-sheet { width: 100%; padding: 34rpx 32rpx calc(34rpx + var(--safe-bottom)); background: var(--card); border-radius: 28rpx 28rpx 0 0; }
.delivery-sheet-title { display: block; color: var(--text); font-size: 32rpx; font-weight: 750; }
.delivery-sheet-desc { display: block; margin-top: 10rpx; color: var(--text-sub); font-size: 22rpx; line-height: 1.5; }
.ssh-input { box-sizing: border-box; width: 100%; min-height: 190rpx; max-height: 360rpx; margin-top: 24rpx; padding: 22rpx; color: var(--text); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: 14rpx; font-size: 25rpx; line-height: 1.55; }
.delivery-security-hint { display: block; margin-top: 14rpx; color: var(--text-dim); font-size: 20rpx; line-height: 1.5; }
.delivery-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 18rpx; margin-top: 26rpx; }
.delivery-cancel, .delivery-submit { min-height: 82rpx; display: flex; align-items: center; justify-content: center; border-radius: 14rpx; font-size: 27rpx; font-weight: 700; }
.delivery-cancel { color: var(--text-sub); background: var(--bg-2); }
.delivery-submit { color: #fff; background: var(--primary); }
.delivery-submit.disabled { opacity: .5; }
</style>
