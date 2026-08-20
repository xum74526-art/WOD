<template>
  <view class="page">
    <AppNavBar :title="t('k_d2523179')" />
    <view class="shell">
      <view class="seg-wrap">
        <SegmentedControl :items="['待交付', '已交付', '已完成']" :model-value="tab" @update:model-value="onTab" />
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
          <text class="og">{{ o.order_no }} · {{ o.gpu_model }} × {{ o.quantity || 1 }} · {{ fmtCH(o.amount) }}</text>
          <text class="os" v-if="o.ssh_info">SSH: {{ o.ssh_info.slice(0, 40) }}...</text>
        </view>
        <view class="or" v-if="o.status === 'paid'">
          <view class="btn-deliver" @tap="showDeliver(o.id)">{{ t('k_d550798d') }}</view>
        </view>
        <view class="or" v-else-if="o.status === 'delivering'">
          <text class="os-text">{{ t('k_edec682e') }}</text>
        </view>
      </view>
    </view>

    <ConfirmSheet :visible="showSheet" :title="t('k_598045cb')" :desc="t('k_a06ac69f')" :confirmText="t('k_da4e4efa')" @cancel="showSheet = false" @confirm="onDeliver">
      <view class="ssh-form">
        <textarea class="ssh-input" v-model="sshText" :placeholder="t('k_3220447b')" placeholder-class="ph" maxlength="300" />
      </view>
    </ConfirmSheet>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { request } from '@/api/request'
import type { OrderItem } from '@/api/order'
import AppNavBar from '@/components/AppNavBar.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import EmptyState from '@/components/EmptyState.vue'
import ConfirmSheet from '@/components/ConfirmSheet.vue'
import { fmtCH } from '@/utils/format'
import { useI18nStore } from '@/store/i18n'
import { localizeProductName } from '@/utils/localize-content'

const i18n = useI18nStore()
const { t } = i18n
const list = ref<OrderItem[]>([])
const loading = ref(true)
const loadError = ref(false)
const tab = ref(0)
const showSheet = ref(false)
const sshText = ref('')
const deliveringId = ref(0)

const STATUS_MAP = ['paid', 'delivering', 'completed']

async function load() {
  loading.value = true
  loadError.value = false
  list.value = []
  try {
    const canonicalStatus = ['confirmed', 'delivered', 'completed'][tab.value]
    const rows = await request<any[]>({ url: '/supplier/orders', data: { status: canonicalStatus, page_size: 100 } })
    list.value = rows.map(row => ({
      ...row,
      cycle_days: Math.max(1, Math.ceil(Number(row.duration_hours || 24) / 24)),
      amount: Number(row.amount || 0),
      product_name: row.snapshot?.product_name || row.snapshot?.server_name || `#${row.product_id || ''}`,
      gpu_model: row.snapshot?.gpu_model || '',
      status: row.status === 'confirmed' ? 'paid' : row.status === 'delivered' ? 'delivering' : row.status,
    }))
  } catch { loadError.value = true }
  loading.value = false
}
onShow(() => load())
function onTab(v: number) { tab.value = v; load() }

function statusText(s: string) {
  const m: Record<string, string> = { paid: '待交付', delivering: '已交付', completed: '已完成', canceled: '已取消' }
  return t(m[s] || s)
}
function statusType(s: string): any {
  const m: Record<string, string> = { paid: 'running', delivering: 'running', completed: 'done', canceled: 'canceled' }
  return m[s] || 'default'
}

function showDeliver(id: number) {
  deliveringId.value = id
  sshText.value = ''
  showSheet.value = true
}

async function onDeliver() {
  showSheet.value = false
  try {
    const order = await request<any>({ url: `/supplier/orders/${deliveringId.value}`, silent: true })
    await request({
      url: `/supplier/orders/${deliveringId.value}/start-delivery`,
      method: 'POST',
      data: { version: order.version, note: '移动端发起统一 Agent 交付流程' },
    })
    uni.showToast({ title: t('已进入交付流程'), icon: 'success' })
    await load()
  } catch {}
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
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
.os { display: block; color: var(--text-dim); font-size: 22rpx; margin-top: 8rpx; }
.or { flex-shrink: 0; }
.btn-deliver { background: var(--primary); color: #fff; padding: 16rpx 32rpx; border-radius: var(--radius); font-size: 26rpx; font-weight: 600; }
.os-text { color: var(--text-sub); font-size: 24rpx; }
.ssh-form { padding: 16rpx 0; }
.ssh-input { width: 100%; min-height: 140rpx; background: var(--bg); border-radius: var(--radius); padding: 20rpx; color: var(--text); font-size: 26rpx; line-height: 1.5; border: 1rpx solid var(--border); }
.ph { color: var(--text-dim); }
</style>
