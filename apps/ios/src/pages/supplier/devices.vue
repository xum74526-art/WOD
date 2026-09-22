<template>
  <view class="page">
    <AppNavBar :title="t('merchantResourceManagement')" />
    <view class="seg-wrap">
      <SegmentedControl :items="segmentItems" :model-value="filterIdx" @update:model-value="onFilter" />
    </view>
    <view class="shell">
      <view v-if="loading && !devices.length" class="state">{{ t('loading') }}</view>
      <view v-else-if="loadError && !devices.length" class="load-error">
        <text>{{ t('listLoadFailedDesc') }}</text>
        <text class="load-retry" @tap="load">{{ t('retry') }}</text>
      </view>
      <view v-else-if="!devices.length" class="card ph">
        <EmptyState :text="t('该分类下暂无设备')" />
      </view>
      <view v-for="device in devices" :key="device.id" class="card drow">
        <image class="dimg" :src="deviceImage(device)" mode="aspectFill" @error="markImageFailed(device.id)" />
        <view class="dbody">
          <view class="dtop">
            <text class="dn">{{ localizeProductName(device.name, i18n.lang) }}</text>
            <view class="badge" :class="device.list_status === 'on' ? 'b-on' : 'b-off'">
              {{ t(device.list_status === 'on' ? 'onSale2' : 'offShelf') }}
            </view>
          </view>
          <text class="dg">
            {{ device.gpu_model }} · {{ device.memory }} ·
            {{ localizeRegionName(device.region, i18n.lang) }} {{ localizeRegionName(device.city, i18n.lang) }}
          </text>
          <view class="dinfo">
            <text class="di price-value">{{ fmtCardHours(device.price) }} {{ t('cardHourPerGpuHour') }}</text>
            <text class="di">{{ t('可租 {count}', { count: device.stock }) }}</text>
            <text class="di">{{ t('{count} 个订单', { count: device.order_count }) }}</text>
          </view>
          <view class="dactions" :class="{ 'action-disabled': busyId === device.id }">
            <view v-if="device.list_status === 'on'" class="mini-btn warn" @tap="onToggle(device, 'off')">{{ t('delist') }}</view>
            <view v-else class="mini-btn primary" @tap="onToggle(device, 'on')">{{ t('relist') }}</view>
            <view class="mini-btn ghost" @tap="onEdit(device)">{{ t('edit') }}</view>
          </view>
        </view>
      </view>
    </view>

    <BottomActionBar>
      <view class="add-btn" @tap="goAdd">＋ {{ t('addDevice') }}</view>
    </BottomActionBar>

    <ConfirmSheet
      :visible="sheet.show"
      :title="sheet.title"
      :desc="sheet.desc"
      :confirm-text="sheet.confirmText"
      @confirm="sheet.onConfirm"
      @cancel="closeConfirm"
    />

    <view v-if="editShow" class="edit-mask" @tap="closeEdit">
      <view class="edit-sheet" @tap.stop>
        <text class="edit-title">{{ t('editResource') }}</text>
        <text class="edit-subtitle">{{ editTarget?.gpu_model }} · {{ editTarget?.memory }}</text>
        <view class="edit-field">
          <text class="edit-label">{{ t('productName') }}</text>
          <input v-model="editForm.name" class="edit-input" maxlength="128" :placeholder="t('enterProductName')" />
        </view>
        <view class="edit-field">
          <text class="edit-label">{{ t('supplierPriceLabel') }}</text>
          <input v-model="editForm.price" class="edit-input" type="digit" :placeholder="t('enterSupplierPrice')" @input="onPriceInput" />
        </view>
        <view class="edit-field">
          <text class="edit-label">{{ t('stock') }}</text>
          <input v-model="editForm.stock" class="edit-input" type="number" :placeholder="t('enterSupplierStock')" />
        </view>
        <view class="edit-btns" :class="{ 'action-disabled': editSaving }">
          <view class="edit-cancel" @tap="closeEdit">{{ t('cancel') }}</view>
          <view class="edit-save" @tap="onSaveEdit">{{ t(editSaving ? 'loading' : 'save') }}</view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import {
  getSupplierDevices,
  updateSupplierDevice,
  type SupplierDeviceItem,
  type SupplierDeviceUpdateInput,
} from '@/api/supplier'
import { ApiRequestError } from '@/api/request'
import AppNavBar from '@/components/AppNavBar.vue'
import BottomActionBar from '@/components/BottomActionBar.vue'
import ConfirmSheet from '@/components/ConfirmSheet.vue'
import EmptyState from '@/components/EmptyState.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import { useI18nStore } from '@/store/i18n'
import { fmtCardHours, formatAmount } from '@/utils/format'
import { localizeProductName } from '@/utils/localize-content'
import { navigateTo } from '@/utils/nav'
import { fallbackProductImage, resolveProductImage } from '@/utils/product-image'
import { localizeRegionName } from '@/utils/region-name'

const i18n = useI18nStore()
const { t, localizedErrorMessage } = i18n
const devices = ref<SupplierDeviceItem[]>([])
const failedImages = ref<Record<number, boolean>>({})
const loading = ref(false)
const loadError = ref(false)
const filterIdx = ref(0)
const busyId = ref<number | null>(null)
const FILTER_MAP: Array<'on' | 'off' | 'all'> = ['on', 'off', 'all']
const segmentItems = computed(() => [t('onSale2'), t('offShelf'), t('allDevices')])
let loadVersion = 0

const editShow = ref(false)
const editSaving = ref(false)
const editTarget = ref<SupplierDeviceItem | null>(null)
const editForm = reactive({ name: '', price: '', stock: '' })
const sheet = reactive({ show: false, title: '', desc: '', confirmText: 'confirm', onConfirm: () => {} })

async function load() {
  const version = ++loadVersion
  loading.value = true
  loadError.value = false
  try {
    const result = await getSupplierDevices(FILTER_MAP[filterIdx.value])
    if (version !== loadVersion) return
    devices.value = result
    failedImages.value = {}
  } catch {
    if (version === loadVersion) loadError.value = true
  } finally {
    if (version === loadVersion) loading.value = false
  }
}

onShow(load)

function onFilter(value: number) {
  filterIdx.value = value
  devices.value = []
  load()
}

function closeConfirm() {
  if (busyId.value === null) sheet.show = false
}

function onToggle(device: SupplierDeviceItem, status: 'on' | 'off') {
  if (busyId.value !== null) return
  const isDelist = status === 'off'
  sheet.title = isDelist ? 'confirmDelist' : 'confirmRelist'
  sheet.desc = t(isDelist ? 'delistResourceDesc' : 'relistResourceDesc', { name: device.name })
  sheet.confirmText = isDelist ? 'delist' : 'relist'
  sheet.onConfirm = async () => {
    if (busyId.value !== null) return
    busyId.value = device.id
    try {
      await updateSupplierDevice(device.id, device.version, { status })
      sheet.show = false
      uni.showToast({ title: t(isDelist ? '已下架' : '已上架'), icon: 'success' })
      await load()
    } catch (error) {
      if (!(await refreshAfterConflict(error))) toastError(error)
    } finally {
      busyId.value = null
    }
  }
  sheet.show = true
}

function onEdit(device: SupplierDeviceItem) {
  if (busyId.value !== null) return
  editTarget.value = device
  editForm.name = device.name
  editForm.price = formatAmount(device.price, false)
  editForm.stock = String(device.stock)
  editShow.value = true
}

function closeEdit() {
  if (editSaving.value) return
  editShow.value = false
  editTarget.value = null
}

function normalizePriceInput(value: unknown): string {
  const raw = String(value ?? '').replace(/[^\d.]/g, '')
  const dotIndex = raw.indexOf('.')
  if (dotIndex < 0) return raw.slice(0, 6)
  const integer = (raw.slice(0, dotIndex) || '0').slice(0, 6)
  const fraction = raw.slice(dotIndex + 1).replace(/\./g, '').slice(0, 3)
  return `${integer}.${fraction}`
}

function onPriceInput(event: any) {
  const value = normalizePriceInput(event.detail?.value)
  editForm.price = value
  return value
}

async function onSaveEdit() {
  if (!editTarget.value || editSaving.value) return
  const name = editForm.name.trim()
  if (name.length < 2) {
    uni.showToast({ title: t('enterProductName'), icon: 'none' })
    return
  }
  const priceInCardHours = Number(editForm.price)
  if (!Number.isFinite(priceInCardHours) || priceInCardHours <= 0 || priceInCardHours > 100000) {
    uni.showToast({ title: t('invalidSupplierPrice'), icon: 'none' })
    return
  }
  const stock = Number(editForm.stock)
  if (!Number.isInteger(stock) || stock < 0 || stock > 100000) {
    uni.showToast({ title: t('invalidSupplierStock'), icon: 'none' })
    return
  }
  const changes: SupplierDeviceUpdateInput = {}
  if (name !== editTarget.value.name) changes.name = name
  if (Math.abs(priceInCardHours - Number(editTarget.value.price)) > 0.0000001) changes.price = priceInCardHours
  if (stock !== editTarget.value.stock) changes.stock = stock
  if (!Object.keys(changes).length) {
    closeEdit()
    return
  }
  editSaving.value = true
  busyId.value = editTarget.value.id
  try {
    await updateSupplierDevice(editTarget.value.id, editTarget.value.version, changes)
    editShow.value = false
    editTarget.value = null
    uni.showToast({ title: t('saved'), icon: 'success' })
    await load()
  } catch (error) {
    if (!(await refreshAfterConflict(error))) toastError(error)
  } finally {
    editSaving.value = false
    busyId.value = null
  }
}

function deviceImage(device: Pick<SupplierDeviceItem, 'id' | 'image_url' | 'gpu_model'>): string {
  return failedImages.value[device.id]
    ? fallbackProductImage(device.gpu_model)
    : resolveProductImage(device.image_url, device.gpu_model)
}

function markImageFailed(id: number) {
  if (!failedImages.value[id]) failedImages.value = { ...failedImages.value, [id]: true }
}

function toastError(error: unknown) {
  uni.showToast({ title: localizedErrorMessage(error, '操作失败'), icon: 'none' })
}

async function refreshAfterConflict(error: unknown): Promise<boolean> {
  if (!(error instanceof ApiRequestError) || error.statusCode !== 409) return false
  sheet.show = false
  editShow.value = false
  editTarget.value = null
  await load()
  uni.showToast({ title: t('resourceChangedRefresh'), icon: 'none' })
  return true
}

function goAdd() {
  navigateTo('/pages/supplier/product-create')
}
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
.dimg { width: 120rpx; height: 120rpx; border-radius: 12rpx; flex-shrink: 0; background: var(--bg-2); }
.dbody { flex: 1; min-width: 0; }
.dtop { display: flex; align-items: center; gap: 12rpx; }
.dn { min-width: 0; flex: 1; color: var(--text); font-size: 28rpx; font-weight: 650; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.badge { flex-shrink: 0; padding: 4rpx 14rpx; border-radius: 8rpx; font-size: 20rpx; font-weight: 600; }
.b-on { background: var(--up-soft); color: var(--up); }
.b-off { background: rgba(156,163,175,.15); color: var(--text-dim); }
.dg { display: block; color: var(--text-sub); font-size: 22rpx; margin-top: 8rpx; }
.dinfo { display: flex; flex-wrap: wrap; gap: 8rpx 22rpx; margin-top: 12rpx; }
.di { color: var(--text-sub); font-size: 22rpx; font-variant-numeric: tabular-nums; }
.price-value { width: 100%; color: var(--text); font-size: 24rpx; font-weight: 650; }
.dactions { display: flex; gap: 14rpx; margin-top: 18rpx; }
.mini-btn { min-width: 88rpx; padding: 10rpx 22rpx; text-align: center; border-radius: 24rpx; font-size: 22rpx; font-weight: 600; }
.mini-btn.warn { background: rgba(239,68,68,.08); color: var(--down); }
.mini-btn.primary { background: var(--primary); color: #fff; }
.mini-btn.ghost { background: var(--bg-2); color: var(--text-sub); border: 1rpx solid var(--border); }
.add-btn { min-height: 92rpx; display: flex; align-items: center; justify-content: center; background: var(--primary); color: #fff; border-radius: var(--radius); font-size: 30rpx; font-weight: 700; }
.action-disabled { opacity: .5; pointer-events: none; }
.edit-mask { position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 200; display: flex; align-items: flex-end; }
.edit-sheet { width: 100%; box-sizing: border-box; background: var(--card); border-radius: 30rpx 30rpx 0 0; padding: 38rpx 32rpx calc(38rpx + var(--safe-bottom)); }
.edit-title { display: block; color: var(--text); font-size: 34rpx; font-weight: 700; }
.edit-subtitle { display: block; color: var(--text-sub); font-size: 24rpx; margin: 8rpx 0 28rpx; }
.edit-field { margin-bottom: 22rpx; }
.edit-label { display: block; margin-bottom: 10rpx; color: var(--text-sub); font-size: 23rpx; }
.edit-input { box-sizing: border-box; width: 100%; height: 82rpx; padding: 0 22rpx; color: var(--text); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); font-size: 28rpx; }
.edit-btns { display: flex; gap: 16rpx; margin-top: 30rpx; }
.edit-cancel, .edit-save { flex: 1; min-height: 84rpx; display: flex; align-items: center; justify-content: center; border-radius: var(--radius); font-size: 28rpx; }
.edit-cancel { background: var(--bg-2); color: var(--text-sub); border: 1rpx solid var(--border); }
.edit-save { background: var(--primary); color: #fff; font-weight: 700; }
</style>
