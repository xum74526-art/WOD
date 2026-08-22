<template>
  <view class="page">
    <AppNavBar :title="t('addressManage')" />
    <view class="shell">
      <view v-if="loading && !list.length" class="load-state">{{ t('loading') }}</view>
      <view v-else-if="loadError && !list.length" class="load-state load-error">
        <text>{{ t('dataUnavailable') }}</text>
        <view class="load-retry" role="button" @tap="load">{{ t('retry') }}</view>
      </view>
      <view v-else-if="!list.length" class="card ph"><EmptyState text="暂无地址" /></view>
      <view v-for="a in list" :key="a.id" class="card arow" :class="{ default: a.is_default }" @tap="onEdit(a)">
        <view class="al">
          <view class="an-row">
            <text class="an">{{ a.name }}</text>
            <text class="aphone">{{ a.phone }}</text>
            <text v-if="a.label" class="alabel">{{ t(a.label) }}</text>
            <text v-if="a.is_default" class="adefault-tag">{{ t('k_18c63459') }}</text>
          </view>
          <text class="ad">{{ localizeRegionName(a.province, i18n.lang) }} {{ localizeRegionName(a.city, i18n.lang) }} {{ localizeRegionName(a.district, i18n.lang) }} {{ a.detail }}</text>
        </view>
      </view>

      <view class="btn-add" v-if="!showForm" @tap="onAddNew">+ {{ t('添加地址') }}</view>

      <!-- 添加/编辑表单 -->
      <view class="card form" v-if="showForm">
        <text class="form-title">{{ t(editingId ? '编辑地址' : '新增地址') }}</text>
        <view class="field">
          <text class="flabel">{{ t('k_6aea70a3') }}</text>
          <input class="finput" v-model="form.name" :placeholder="t('k_8093e392')" placeholder-class="ph" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('k_8098e2b4') }}</text>
          <input class="finput" v-model="form.phone" type="number" :placeholder="t('k_6e4f4b33')" placeholder-class="ph" maxlength="11" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('k_65d3ab77') }}</text>
          <picker mode="multiSelector" :range="multiRange" :value="multiValue" @change="onMultiChange" @columnchange="onColumnChange">
            <view class="finput picker">{{ regionText || t('请选择省市区') }}</view>
          </picker>
        </view>
        <view class="field">
          <text class="flabel">{{ t('k_61a0ec8a') }}</text>
          <input class="finput" v-model="form.detail" :placeholder="t('k_00e9a24d')" placeholder-class="ph" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('k_1d2fd338') }}</text>
          <view class="label-row">
            <text v-for="l in labels" :key="l" class="label-opt" :class="{ active: form.label === l }" @tap="form.label = form.label === l ? '' : l">{{ t(l) }}</text>
          </view>
        </view>
        <view class="field" v-if="list.length > 0">
          <view class="default-row">
            <text class="flabel">{{ t('k_e4749162') }}</text>
            <switch :checked="form.is_default" @change="form.is_default = !form.is_default" />
          </view>
        </view>
        <view class="btn-row">
          <view v-if="editingId" class="btn-del" @tap="onDelete(editingId)">{{ t('delete') }}</view>
          <view class="btn-primary" :class="{ disabled: submitting }" @tap="onSave">{{ t(submitting ? '保存中...' : '保存') }}</view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getAddresses, addAddress, updateAddress, deleteAddress, setDefaultAddress, type AddressItem } from '@/api/address'
import { regionData } from '@/utils/region-data'
import { localizeRegionName } from '@/utils/region-name'
import AppNavBar from '@/components/AppNavBar.vue'
import EmptyState from '@/components/EmptyState.vue'
import { useI18nStore } from '@/store/i18n'

const i18n = useI18nStore()
const { t } = i18n
const list = ref<AddressItem[]>([])
const loading = ref(true)
const loadError = ref(false)
const showForm = ref(false)
const editingId = ref<number | null>(null)
const submitting = ref(false)
const labels = ['家', '公司', '学校']
const form = reactive({ name: '', phone: '', province: '', city: '', district: '', detail: '', label: '', is_default: false })

// 三列选择器（省+市+区）
const multiValue = ref<number[]>([0, 0, 0])
const provinceList = computed(() => regionData.map(p => p.name))
const cityList = computed(() => regionData[multiValue.value[0]]?.children?.map(c => c.name) || [])
const districtList = computed(() => regionData[multiValue.value[0]]?.children?.[multiValue.value[1]]?.children?.map(d => d.name) || [])
const multiRange = computed(() => [
  provinceList.value.map(name => localizeRegionName(name, i18n.lang)),
  cityList.value.map(name => localizeRegionName(name, i18n.lang)),
  districtList.value.map(name => localizeRegionName(name, i18n.lang)),
])

const regionText = computed(() => form.province
  ? [form.province, form.city, form.district].map(name => localizeRegionName(name, i18n.lang)).join(' ')
  : '')

function onColumnChange(e: any) {
  const { column, value } = e.detail
  const arr = [...multiValue.value]
  arr[column] = value
  if (column === 0) { arr[1] = 0; arr[2] = 0 }
  if (column === 1) { arr[2] = 0 }
  multiValue.value = arr
}

function onMultiChange(e: any) {
  const v = e.detail.value as number[]
  multiValue.value = v
  form.province = provinceList.value[v[0]] || ''
  form.city = cityList.value[v[1]] || ''
  form.district = districtList.value[v[2]] || ''
}

// 编辑时同步 multiValue
watch(() => form.province, () => {
  if (!form.province) { multiValue.value = [0, 0, 0]; return }
  const pi = provinceList.value.indexOf(form.province)
  if (pi >= 0) {
    const ci = regionData[pi]?.children?.findIndex(c => c.name === form.city) ?? 0
    const di = regionData[pi]?.children?.[ci]?.children?.findIndex(d => d.name === form.district) ?? 0
    multiValue.value = [pi, ci >= 0 ? ci : 0, di >= 0 ? di : 0]
  }
})

async function load() {
  loading.value = true
  loadError.value = false
  try { list.value = await getAddresses() }
  catch { loadError.value = true }
  finally { loading.value = false }
}
onShow(() => load())

function resetForm() {
  form.name = form.phone = form.province = form.city = form.district = form.detail = form.label = ''
  form.is_default = false
  editingId.value = null
}

function onAddNew() {
  resetForm()
  form.is_default = list.value.length === 0
  showForm.value = true
}

function onEdit(a: AddressItem) {
  editingId.value = a.id
  form.name = a.name
  form.phone = a.phone
  form.province = a.province
  form.city = a.city
  form.district = a.district
  form.detail = a.detail
  form.label = a.label || ''
  form.is_default = a.is_default
  showForm.value = true
}

function onRegionChange(e: any) {
  const [province, city, district] = e.detail.value || []
  form.province = province || ''
  form.city = city || ''
  form.district = district || ''
}

async function onSave() {
  if (submitting.value) return
  if (!form.name) { uni.showToast({ title: t('请输入收货人'), icon: 'none' }); return }
  if (!form.phone || form.phone.length !== 11) { uni.showToast({ title: t('请输入正确手机号'), icon: 'none' }); return }
  if (!form.province) { uni.showToast({ title: t('请选择所在地区'), icon: 'none' }); return }
  if (!form.detail) { uni.showToast({ title: t('请输入详细地址'), icon: 'none' }); return }

  submitting.value = true
  try {
    const data = { ...form, label: form.label || undefined }
    if (editingId.value) {
      // 编辑
      if (form.is_default) await setDefaultAddress(editingId.value)
      await updateAddress(editingId.value, data)
      uni.showToast({ title: t('修改成功'), icon: 'success' })
    } else {
      // 新增
      await addAddress(data)
      if (form.is_default && list.value.length > 0) {
        // 新增的设为默认需要单独调用
      }
      uni.showToast({ title: t('添加成功'), icon: 'success' })
    }
    showForm.value = false
    resetForm()
    await load()
  } catch {}
  submitting.value = false
}

function onDelete(id: number) {
  uni.showModal({
    title: t('提示'), content: t('确认删除该地址？'),
    success: async (r) => {
      if (r.confirm) {
        try { await deleteAddress(id); showForm.value = false; resetForm(); await load() } catch {}
      }
    }
  })
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--border); }
.load-state { min-height: 180rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 26rpx; }
.load-error { flex-direction: column; gap: 18rpx; }
.load-retry { min-height: 68rpx; padding: 0 28rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: var(--radius); font-weight: 700; }
.ph { padding: 60rpx 0; }
.arow { padding: 28rpx 32rpx; margin-bottom: 16rpx; }
.arow.default { background: var(--card); border-color: rgba(24,175,196,0.2); }
.al { flex: 1; }
.an-row { display: flex; align-items: center; gap: 12rpx; }
.an { color: var(--text); font-size: 28rpx; font-weight: 600; }
.aphone { color: var(--text-sub); font-size: 26rpx; }
.alabel { color: var(--primary); font-size: 20rpx; background: var(--primary-soft); padding: 2rpx 12rpx; border-radius: 6rpx; }
.adefault-tag { color: var(--up); font-size: 20rpx; background: var(--up-soft); padding: 2rpx 12rpx; border-radius: 6rpx; }
.ad { color: var(--text-sub); font-size: 24rpx; margin-top: 12rpx; display: block; line-height: 1.5; }
.btn-add { text-align: center; padding: 28rpx; border: 1rpx dashed var(--border); color: var(--primary); border-radius: var(--radius); font-size: 28rpx; margin-top: 16rpx; }

.form { padding: 24rpx 32rpx; margin-top: 16rpx; }
.form-title { color: var(--text); font-size: 32rpx; font-weight: 700; display: block; margin-bottom: 24rpx; }
.field { margin-bottom: 28rpx; }
.flabel { color: var(--text-sub); font-size: 24rpx; display: block; margin-bottom: 12rpx; }
.finput { color: var(--text); font-size: 30rpx; }
.picker { color: var(--text-sub); }
.picker:active { opacity: 0.6; }
.ph { color: var(--text-dim); }

.label-row { display: flex; gap: 16rpx; }
.label-opt { padding: 8rpx 28rpx; border-radius: 24rpx; background: var(--bg); color: var(--text-sub); font-size: 24rpx; border: 1rpx solid var(--border); }
.label-opt.active { background: var(--primary); color: #fff; border-color: var(--primary); }

.default-row { display: flex; justify-content: space-between; align-items: center; }

.btn-row { display: flex; gap: 16rpx; margin-top: 8rpx; }
.btn-del { flex: 1; text-align: center; padding: 24rpx 0; border-radius: var(--radius); background: var(--down-soft); color: var(--down); font-size: 28rpx; }
.btn-primary { flex: 2; text-align: center; padding: 24rpx 0; border-radius: var(--radius); background: linear-gradient(135deg, var(--primary), var(--primary)); color: #fff; font-size: 28rpx; font-weight: 600; }
.btn-primary.disabled { opacity: 0.4; }
</style>
