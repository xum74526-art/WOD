<template>
  <view class="page">
    <AppNavBar :title="t('k_b1a8beb8')" />
    <view class="seg-wrap">
      <SegmentedControl :items="['在售', '已下架', '全部']" :model-value="filterIdx" @update:model-value="onFilter" />
    </view>
    <view class="shell">
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
          <text class="dg">{{ d.gpu_model }} · {{ d.memory }} · {{ tr(d.region) }} {{ localizeRegionName(d.city, i18n.lang) }}</text>
          <view class="dinfo">
            <text class="di">{{ fmtCH(d.price) }}/h</text>
            <text class="di">{{ t('可租 {count}', { count: d.stock }) }}</text>
            <text class="di">{{ t('{count} 个订单', { count: d.order_count }) }}</text>
          </view>
          <view class="dactions">
            <view v-if="d.list_status === 'on'" class="mini-btn warn" @tap="onToggle(d, 'off')">{{ t('k_d2379a56') }}</view>
            <view v-else class="mini-btn primary" @tap="onToggle(d, 'on')">{{ t('k_4a50988f') }}</view>
            <view class="mini-btn ghost" @tap="onEdit(d)">{{ t('edit') }}</view>
          </view>
        </view>
      </view>
    </view>
    <BottomActionBar><view class="add-btn" @tap="goAdd">＋ {{ t('上架新设备') }}</view></BottomActionBar>

    <!-- 下架/上架确认 -->
    <ConfirmSheet
      :visible="sheet.show"
      :title="sheet.title"
      :desc="sheet.desc"
      :confirm-text="sheet.confirmText"
      @confirm="sheet.onConfirm"
      @cancel="sheet.show = false"
    />

    <!-- 编辑价格/库存 -->
    <view v-if="editShow" class="edit-mask" @tap="editShow = false">
      <view class="edit-sheet" @tap.stop>
        <text class="edit-title">{{ t('k_9f10a2b2') }}</text>
        <text class="edit-name">{{ localizeProductName(editTarget?.name || '', i18n.lang) }}</text>
        <view class="edit-field">
          <text class="edit-label">{{ t('k_7487aead') }}</text>
          <input class="edit-input" type="digit" v-model="editForm.price" :placeholder="t('k_6f2838fe')" @input="onPriceInput" />
        </view>
        <view class="edit-field">
          <text class="edit-label">{{ t('k_40a4b798') }}</text>
          <input class="edit-input" type="number" v-model="editForm.stock" :placeholder="t('k_fa787294')" />
        </view>
        <view class="edit-btns">
          <view class="edit-cancel" @tap="editShow = false">{{ t("cancel") }}</view>
          <view class="edit-save" @tap="onSaveEdit">{{ t("save") }}</view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { request } from '@/api/request'
import AppNavBar from '@/components/AppNavBar.vue'
import EmptyState from '@/components/EmptyState.vue'
import BottomActionBar from '@/components/BottomActionBar.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import ConfirmSheet from '@/components/ConfirmSheet.vue'
import { navigateTo as nav } from '@/utils/nav'
import { fmtCH, formatNumberInput, fromCardHours, toCardHours } from '@/utils/format'
import { useI18nStore } from '@/store/i18n'
import { localizeRegionName } from '@/utils/region-name'
import { localizeProductName } from '@/utils/localize-content'
import { fallbackProductImage, resolveProductImage } from '@/utils/product-image'

const i18n = useI18nStore()
const { t, tr } = i18n
interface DeviceItem {
  id: number
  name: string
  gpu_model: string
  memory: string
  price: number
  stock: number
  region: string
  city: string
  order_count: number
  status: string
  list_status: string
  image_url: string | null
}

const devices = ref<DeviceItem[]>([])
const failedImages = ref<Record<number, boolean>>({})
const loading = ref(false)
const loadError = ref(false)
const filterIdx = ref(0)
const FILTER_MAP = ['on', 'off', 'all']

const editShow = ref(false)
const editTarget = ref<DeviceItem | null>(null)
const editForm = reactive({ price: '', stock: '' })

const sheet = reactive({
  show: false,
  title: '',
  desc: '',
  confirmText: t('确定'),
  onConfirm: () => {},
})

async function load() {
  loading.value = true
  loadError.value = false
  devices.value = []
  failedImages.value = {}
  try {
    devices.value = await request({ url: '/supplier/devices', data: { status_filter: FILTER_MAP[filterIdx.value] } })
  } catch { loadError.value = true }
  loading.value = false
}
onShow(() => load())

function onFilter(v: number) {
  filterIdx.value = v
  load()
}

function onToggle(d: DeviceItem, newStatus: string) {
  const isDelist = newStatus === 'off'
  sheet.title = t(isDelist ? '确认下架' : '确认上架')
  sheet.desc = isDelist
    ? t('下架后「{name}」将不再展示在市场中，用户无法新购。已售订单不受影响。', { name: d.name })
    : t('上架后「{name}」将重新展示在市场中供用户购买。', { name: d.name })
  sheet.confirmText = t(isDelist ? '下架' : '上架')
  sheet.onConfirm = async () => {
    sheet.show = false
    try {
      await request({ url: `/supplier/devices/${d.id}`, method: 'PUT', data: { status: newStatus } })
      d.list_status = newStatus
      uni.showToast({ title: t(isDelist ? '已下架' : '已上架'), icon: 'success' })
      if (filterIdx.value !== 2) load()
    } catch {
      uni.showToast({ title: t('操作失败'), icon: 'none' })
    }
  }
  sheet.show = true
}

function onEdit(d: DeviceItem) {
  editTarget.value = d
  editForm.price = formatNumberInput(toCardHours(d.price))
  editForm.stock = String(d.stock)
  editShow.value = true
}

function deviceImage(device: Pick<DeviceItem, 'id' | 'image_url' | 'gpu_model'>): string {
  return failedImages.value[device.id]
    ? fallbackProductImage(device.gpu_model)
    : resolveProductImage(device.image_url, device.gpu_model)
}

function markImageFailed(id: number) {
  if (!failedImages.value[id]) failedImages.value = { ...failedImages.value, [id]: true }
}

function normalizePriceInput(value: unknown): string {
  const raw = String(value ?? '').replace(/[^\d.]/g, '')
  const dotIndex = raw.indexOf('.')
  if (dotIndex < 0) return raw
  const integer = raw.slice(0, dotIndex) || '0'
  const fraction = raw.slice(dotIndex + 1).replace(/\./g, '').slice(0, 2)
  return `${integer}.${fraction}`
}

function onPriceInput(event: any) {
  const value = normalizePriceInput(event?.detail?.value)
  editForm.price = value
  return value
}

async function onSaveEdit() {
  if (!editTarget.value) return
  const priceInCardHours = Number(editForm.price)
  if (!Number.isFinite(priceInCardHours) || priceInCardHours <= 0) {
    uni.showToast({ title: t('k_6f2838fe'), icon: 'none' })
    return
  }
  const backendPrice = fromCardHours(priceInCardHours)
  try {
    await request({
      url: `/supplier/devices/${editTarget.value.id}`,
      method: 'PUT',
      data: { price: backendPrice, stock: Number(editForm.stock) },
    })
    editTarget.value.price = backendPrice
    editTarget.value.stock = Number(editForm.stock)
    editShow.value = false
    uni.showToast({ title: t('已保存'), icon: 'success' })
  } catch {
    uni.showToast({ title: t('保存失败'), icon: 'none' })
  }
}

function goAdd() { nav('/pages/supplier/product-create') }
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.seg-wrap { padding: 16rpx 32rpx 8rpx; }
.shell { flex: 1; padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
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
.dactions { display: flex; gap: 16rpx; margin-top: 16rpx; }
.mini-btn { padding: 8rpx 28rpx; border-radius: 24rpx; font-size: 22rpx; font-weight: 600; }
.mini-btn.warn { background: rgba(239,68,68,0.08); color: var(--down); }
.mini-btn.primary { background: linear-gradient(135deg, var(--primary), var(--primary)); color: #fff; }
.mini-btn.ghost { background: var(--bg); color: var(--text-sub); border: 1rpx solid var(--border); }
.add-btn { background: linear-gradient(135deg, var(--primary), var(--primary)); color: #fff; text-align: center; padding: 28rpx 0; border-radius: var(--radius); font-size: 30rpx; font-weight: 600; }
.edit-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 200; display: flex; align-items: flex-end; }
.edit-sheet { width: 100%; background: var(--bg); border-radius: 32rpx 32rpx 0 0; padding: 40rpx 32rpx calc(40rpx + var(--safe-bottom)); }
.edit-title { color: var(--text); font-size: 34rpx; font-weight: 700; display: block; margin-bottom: 8rpx; }
.edit-name { color: var(--text-sub); font-size: 26rpx; display: block; margin-bottom: 32rpx; }
.edit-field { margin-bottom: 24rpx; }
.edit-label { color: var(--text); font-size: 26rpx; display: block; margin-bottom: 12rpx; }
.edit-input { width: 100%; height: 80rpx; line-height: 80rpx; background: var(--bg); border-radius: var(--radius); padding: 0 24rpx; color: var(--text); font-size: 28rpx; }
.edit-btns { display: flex; gap: 16rpx; margin-top: 32rpx; }
.edit-cancel { flex: 1; text-align: center; padding: 24rpx 0; border-radius: var(--radius); background: var(--bg); color: var(--text-sub); font-size: 28rpx; }
.edit-save { flex: 1; text-align: center; padding: 24rpx 0; border-radius: var(--radius); background: linear-gradient(135deg, var(--primary), var(--primary)); color: #fff; font-size: 28rpx; font-weight: 600; }
</style>
