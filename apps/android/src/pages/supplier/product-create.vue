<template>
  <view class="page">
    <AppNavBar :title="t('addDevice')" />
    <view class="shell">
      <SectionHeader :title="t('resourceBasics')" />
      <view class="card form">
        <view class="field">
          <text class="flabel">{{ t('productName') }}</text>
          <input v-model="form.name" class="finput" :placeholder="t('enterProductName')" placeholder-class="ph" maxlength="128" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('gpuModel') }}</text>
          <input v-model="form.gpu_model" class="finput" :placeholder="t('enterGpuModel')" placeholder-class="ph" maxlength="64" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('memory') }}</text>
          <input v-model="form.memory" class="finput" :placeholder="t('enterMemory')" placeholder-class="ph" maxlength="32" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('cuda') }}</text>
          <input v-model="form.cuda" class="finput" :placeholder="t('enterCudaOptional')" placeholder-class="ph" maxlength="32" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('supplierPriceLabel') }}</text>
          <input v-model="form.price" class="finput" type="digit" :placeholder="t('enterSupplierPrice')" placeholder-class="ph" @input="onPriceInput" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('stock') }}</text>
          <input v-model="form.stock" class="finput" type="number" :placeholder="t('enterSupplierStock')" placeholder-class="ph" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('region') }}</text>
          <picker :range="displayRegions" range-key="displayName" @change="onRegion">
            <view class="finput picker" :class="{ selected: form.region_code }">
              {{ selectedRegionName || t('selectRegion') }}
            </view>
          </picker>
        </view>
        <view class="field">
          <text class="flabel">{{ t('city') }}</text>
          <input v-model="form.city" class="finput" :placeholder="t('enterCityOptional')" placeholder-class="ph" maxlength="64" />
        </view>
        <view class="field field-last">
          <text class="flabel">{{ t('resourceDescription') }}</text>
          <textarea v-model="form.desc" class="tarea" :placeholder="t('resourceDescriptionOptional')" placeholder-class="ph" maxlength="255" />
        </view>
      </view>
      <view class="submit" :class="{ disabled: submitting }" @tap="onSubmit">
        {{ t(submitting ? 'loading' : 'listResource') }}
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { createSupplierDevice } from '@/api/supplier'
import AppNavBar from '@/components/AppNavBar.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import { useI18nStore } from '@/store/i18n'
import { localizeRegionName } from '@/utils/region-name'
import { navigateBack } from '@/utils/nav'

const i18n = useI18nStore()
const { t, localizedErrorMessage } = i18n
const submitting = ref(false)

const regions = [
  { name: '华北', code: 'north_china' },
  { name: '华东', code: 'east_china' },
  { name: '华中', code: 'central_china' },
  { name: '华南', code: 'south_china' },
  { name: '东北', code: 'northeast_china' },
  { name: '西北', code: 'northwest_china' },
  { name: '西南', code: 'southwest_china' },
]

const displayRegions = computed(() => regions.map(region => ({
  ...region,
  displayName: localizeRegionName(region.name, i18n.lang, region.code),
})))

const form = reactive({
  name: '',
  gpu_model: '',
  memory: '',
  cuda: '',
  price: '',
  stock: '1',
  city: '',
  desc: '',
  region_name: '',
  region_code: '',
})

const selectedRegionName = computed(() => form.region_name
  ? localizeRegionName(form.region_name, i18n.lang, form.region_code)
  : '')

function onRegion(event: { detail: { value: string | number } }) {
  const region = regions[Number(event.detail.value)]
  if (!region) return
  form.region_name = region.name
  form.region_code = region.code
}

function normalizePriceInput(value: unknown): string {
  const raw = String(value ?? '').replace(/[^\d.]/g, '')
  const dotIndex = raw.indexOf('.')
  if (dotIndex < 0) return raw.slice(0, 6)
  const integer = (raw.slice(0, dotIndex) || '0').slice(0, 6)
  const fraction = raw.slice(dotIndex + 1).replace(/\./g, '').slice(0, 4)
  return `${integer}.${fraction}`
}

function onPriceInput(event: any) {
  const value = normalizePriceInput(event.detail?.value)
  form.price = value
  return value
}

function toastError(error: unknown) {
  uni.showToast({ title: localizedErrorMessage(error, '操作失败'), icon: 'none' })
}

async function onSubmit() {
  if (submitting.value) return
  const name = form.name.trim()
  const gpuModel = form.gpu_model.trim()
  const memory = form.memory.trim()
  if (name.length < 2 || gpuModel.length < 2 || !memory) {
    uni.showToast({ title: t('requiredSupplierFields'), icon: 'none' })
    return
  }
  if (!form.region_code) {
    uni.showToast({ title: t('selectRegion'), icon: 'none' })
    return
  }
  const priceInCardHours = Number(form.price)
  if (!Number.isFinite(priceInCardHours) || priceInCardHours <= 0 || priceInCardHours > 100000) {
    uni.showToast({ title: t('invalidSupplierPrice'), icon: 'none' })
    return
  }
  const stock = Number(form.stock)
  if (!Number.isInteger(stock) || stock < 0 || stock > 100000) {
    uni.showToast({ title: t('invalidSupplierStock'), icon: 'none' })
    return
  }

  submitting.value = true
  let listed = false
  try {
    await createSupplierDevice({
      name,
      gpu_model: gpuModel,
      memory,
      cuda: form.cuda.trim() || null,
      price: priceInCardHours,
      stock,
      desc: form.desc.trim() || null,
      region_code: form.region_code,
      region_name: form.region_name,
      city: form.city.trim() || '-',
    })
    listed = true
    uni.showToast({ title: t('listingSuccess'), icon: 'success' })
    setTimeout(() => navigateBack(), 400)
  } catch (error) {
    toastError(error)
  } finally {
    if (!listed) submitting.value = false
  }
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(56rpx + var(--safe-bottom)); }
.card { background: var(--card); border: 1rpx solid var(--card-border); border-radius: var(--radius); }
.form { padding: 10rpx 28rpx; margin-bottom: 28rpx; }
.field { padding: 22rpx 0; border-bottom: 1rpx solid var(--border); }
.field-last { border-bottom: 0; }
.flabel { display: block; margin-bottom: 12rpx; color: var(--text-sub); font-size: 23rpx; }
.finput { min-height: 54rpx; color: var(--text); font-size: 29rpx; line-height: 54rpx; }
.picker { color: var(--text-dim); }
.picker.selected { color: var(--text); }
.tarea { width: 100%; min-height: 150rpx; color: var(--text); font-size: 27rpx; line-height: 1.55; }
.ph { color: var(--text-dim); }
.submit { min-height: 92rpx; display: flex; align-items: center; justify-content: center; color: #fff; background: var(--primary); border-radius: var(--radius); font-size: 30rpx; font-weight: 700; }
.submit.disabled { opacity: .55; }
</style>
