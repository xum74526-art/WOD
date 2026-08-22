<template>
  <view class="page">
    <AppNavBar :title="t('k_d2523179')" />
    <view class="shell">
      <view class="read-only-note">
        <text class="read-only-title">{{ t('mobileMerchantReadOnlyTitle') }}</text>
        <text class="read-only-desc">{{ t('mobileMerchantReadOnlyHint') }}</text>
      </view>
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
        <view class="or" v-if="o.status === 'delivering'">
          <text class="os-text">{{ t('k_edec682e') }}</text>
        </view>
      </view>
    </view>
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
import { fmtCH } from '@/utils/format'
import { useI18nStore } from '@/store/i18n'
import { localizeProductName } from '@/utils/localize-content'

const i18n = useI18nStore()
const { t } = i18n
const list = ref<OrderItem[]>([])
const loading = ref(true)
const loadError = ref(false)
const tab = ref(0)

const STATUS_MAP = ['paid', 'delivering', 'completed']

async function load() {
  loading.value = true
  loadError.value = false
  list.value = []
  try {
    list.value = await request<OrderItem[]>({ url: '/supplier/orders', data: { status_filter: STATUS_MAP[tab.value] } })
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

</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.read-only-note { padding: 20rpx 22rpx; margin: 16rpx 0 18rpx; background: var(--primary-soft); border: 1rpx solid rgba(24,175,196,.2); border-radius: var(--radius); }
.read-only-title { display: block; color: var(--text); font-size: 24rpx; font-weight: 700; }
.read-only-desc { display: block; margin-top: 6rpx; color: var(--text-sub); font-size: 21rpx; line-height: 1.5; }
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
.os-text { color: var(--text-sub); font-size: 24rpx; }
</style>
