<template>
  <view class="page">
    <AppNavBar :title="t('k_b1a8beb8')" />
    <view class="seg-wrap">
      <SegmentedControl :items="['在售', '已下架', '全部']" :model-value="filterIdx" @update:model-value="onFilter" />
    </view>
    <view class="shell">
      <view class="read-only-note">
        <text class="read-only-title">{{ t('mobileMerchantReadOnlyTitle') }}</text>
        <text class="read-only-desc">{{ t('mobileMerchantReadOnlyHint') }}</text>
      </view>
      <view v-if="loading && !devices.length" class="state">{{ t("loading") }}</view>
      <view v-else-if="loadError" class="load-error"><text>{{ t('listLoadFailedDesc') }}</text><text class="load-retry" @tap="load">{{ t('retry') }}</text></view>
      <view v-else-if="!devices.length" class="card ph"><EmptyState :text="t('该分类下暂无设备')" /></view>
      <view v-for="d in devices" :key="d.id" class="card drow">
        <image class="dimg" :src="deviceImage(d)" mode="aspectFill" @error="markImageFailed(d.id)" />
        <view class="dbody">
          <view class="dtop">
            <text class="dn">{{ localizeProductName(d.name, i18n.lang) }}</text>
            <view class="badge" :class="d.list_status === 'on' ? 'b-on' : 'b-off'">
              {{ t(d.list_status === 'on' ? '在售' : '已下架') }}
            </view>
          </view>
          <text class="dg">{{ d.gpu_model }} · {{ d.memory }} · {{ localizeRegionName(d.region, i18n.lang) }} {{ localizeRegionName(d.city, i18n.lang) }}</text>
          <view class="dinfo">
            <text class="di">{{ fmtCH(d.price) }}/h</text>
            <text class="di">{{ t('可租 {count}', { count: d.stock }) }}</text>
            <text class="di">{{ t('{count} 个订单', { count: d.order_count }) }}</text>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getSupplierDevices, type SupplierDeviceItem } from '@/api/supplier'
import AppNavBar from '@/components/AppNavBar.vue'
import EmptyState from '@/components/EmptyState.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import { fmtCH } from '@/utils/format'
import { useI18nStore } from '@/store/i18n'
import { localizeRegionName } from '@/utils/region-name'
import { localizeProductName } from '@/utils/localize-content'
import { fallbackProductImage, resolveProductImage } from '@/utils/product-image'

const i18n = useI18nStore()
const { t } = i18n

const devices = ref<SupplierDeviceItem[]>([])
const failedImages = ref<Record<number, boolean>>({})
const loading = ref(false)
const loadError = ref(false)
const filterIdx = ref(0)
const FILTER_MAP: Array<'on' | 'off' | 'all'> = ['on', 'off', 'all']

async function load() {
  loading.value = true
  loadError.value = false
  devices.value = []
  failedImages.value = {}
  try {
    devices.value = await getSupplierDevices(FILTER_MAP[filterIdx.value])
  } catch { loadError.value = true }
  loading.value = false
}
onShow(() => load())

function onFilter(v: number) {
  filterIdx.value = v
  load()
}

function deviceImage(device: Pick<SupplierDeviceItem, 'id' | 'image_url' | 'gpu_model'>): string {
  return failedImages.value[device.id]
    ? fallbackProductImage(device.gpu_model)
    : resolveProductImage(device.image_url, device.gpu_model)
}

function markImageFailed(id: number) {
  if (!failedImages.value[id]) failedImages.value = { ...failedImages.value, [id]: true }
}

</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.seg-wrap { padding: 16rpx 32rpx 8rpx; }
.shell { flex: 1; padding: 0 32rpx calc(72rpx + var(--safe-bottom)); }
.read-only-note { padding: 20rpx 22rpx; margin: 10rpx 0 18rpx; background: var(--primary-soft); border: 1rpx solid rgba(24,175,196,.2); border-radius: var(--radius); }
.read-only-title { display: block; color: var(--text); font-size: 24rpx; font-weight: 700; }
.read-only-desc { display: block; margin-top: 6rpx; color: var(--text-sub); font-size: 21rpx; line-height: 1.5; }
.state { color: var(--text-sub); text-align: center; padding: 40rpx 0; font-size: 26rpx; }
.load-error { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; padding: 20rpx 24rpx; color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); font-size: 23rpx; line-height: 1.5; }
.load-retry { flex-shrink: 0; color: var(--primary); font-weight: 700; min-height: 64rpx; display: flex; align-items: center; }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--card-border); }
.ph { padding: 60rpx 0; }
.drow { display: flex; padding: 24rpx; margin-bottom: 16rpx; gap: 20rpx; }
.dimg { width: 120rpx; height: 120rpx; border-radius: 12rpx; flex-shrink: 0; }
.dbody { flex: 1; }
.dtop { display: flex; align-items: center; gap: 16rpx; }
.dn { color: var(--text); font-size: 28rpx; font-weight: 600; }
.badge { padding: 4rpx 16rpx; border-radius: 8rpx; font-size: 20rpx; font-weight: 600; }
.b-on { background: var(--up-soft); color: var(--up); }
.b-off { background: rgba(156,163,175,0.15); color: var(--text-dim); }
.dg { display: block; color: var(--text-sub); font-size: 22rpx; margin-top: 8rpx; }
.dinfo { display: flex; gap: 24rpx; margin-top: 12rpx; }
.di { color: var(--text); font-size: 24rpx; font-variant-numeric: tabular-nums; }
</style>
