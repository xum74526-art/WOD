<template>
  <view class="page">
    <AppNavBar :title="t('k_2c336132')" />
    <view class="shell">
      <SectionHeader :title="t('k_b433e6c6')" />
      <view class="card form">
        <view class="field">
          <text class="flabel">{{ t('k_1fd1d5c5') }}</text>
          <input class="finput" v-model="form.name" :placeholder="t('k_1410223c')" placeholder-class="ph" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('GPU 型号') }}</text>
          <input class="finput" v-model="form.gpu_model" :placeholder="t('k_562e44ce')" placeholder-class="ph" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('k_224d9bc8') }}</text>
          <input class="finput" v-model="form.memory" :placeholder="t('k_582fd486')" placeholder-class="ph" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('CUDA 版本') }}</text>
          <input class="finput" v-model="form.cuda" :placeholder="t('k_aa73c35d')" placeholder-class="ph" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('k_02adee49') }}</text>
          <input class="finput" v-model="form.price" type="digit" :placeholder="t('k_a0e0d66a')" placeholder-class="ph" @input="onPriceInput" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('k_40a4b798') }}</text>
          <input class="finput" v-model="form.stock" type="number" :placeholder="t('k_1cd57e1a')" placeholder-class="ph" />
        </view>
        <view class="field">
          <text class="flabel">{{ t("region") }}</text>
          <picker :range="displayRegions" range-key="displayName" @change="onRegion">
            <view class="finput picker">{{ form.region_name ? tr(form.region_name) : t('请选择地区') }}</view>
          </picker>
        </view>
        <view class="field">
          <text class="flabel">{{ t('k_4773d0db') }}</text>
          <input class="finput" v-model="form.city" :placeholder="t('k_ddc641c9')" placeholder-class="ph" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('k_f3b0bd7b') }}</text>
          <input class="finput" v-model="form.image_url" placeholder="/static/gpu/H100.jpg" placeholder-class="ph" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('k_3a35f8c1') }}</text>
          <textarea class="tarea" v-model="form.desc" :placeholder="t('k_73668cf1')" placeholder-class="ph" maxlength="300" />
        </view>
      </view>
      <view class="btn-primary" :class="{ disabled: submitting }" @tap="onSubmit">{{ t(submitting ? '提交中...' : '上架') }}</view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { request } from '@/api/request'
import { navigateBack } from '@/utils/nav'
import AppNavBar from '@/components/AppNavBar.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import { useI18nStore } from '@/store/i18n'
import { fromCardHours } from '@/utils/format'

const { t, tr } = useI18nStore()
const submitting = ref(false)
const regions = [
  { name: '华北', code: 'north_china' },
  { name: '华东', code: 'east_china' },
  { name: '华南', code: 'south_china' },
  { name: '西北', code: 'northwest_china' },
  { name: '西南', code: 'southwest_china' },
]
const displayRegions = computed(() => regions.map(region => ({
  ...region,
  displayName: t(region.name),
})))
const form = reactive({
  name: '', gpu_model: '', memory: '', cuda: '', price: '',
  stock: '1', city: '', image_url: '', desc: '',
  region_name: '', region_code: '',
})

function onRegion(e: any) {
  const r = displayRegions.value[e.detail.value]
  form.region_name = r.name
  form.region_code = r.code
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
  form.price = value
  return value
}

async function onSubmit() {
  if (!form.name || !form.gpu_model || !form.price) {
    uni.showToast({ title: t('请填写完整'), icon: 'none' }); return
  }
  if (!form.region_code) {
    uni.showToast({ title: t('请选择地区'), icon: 'none' }); return
  }
  const priceInCardHours = Number(form.price)
  if (!Number.isFinite(priceInCardHours) || priceInCardHours <= 0) {
    uni.showToast({ title: t('k_6f2838fe'), icon: 'none' }); return
  }
  submitting.value = true
  try {
    await request({
      url: '/supplier/devices', method: 'POST',
      data: {
        name: form.name, gpu_model: form.gpu_model, memory: form.memory || '-',
        cuda: form.cuda || null, price: fromCardHours(priceInCardHours),
        desc: form.desc || '供应商上架算力', image_url: form.image_url || '/static/gpu/gpu.png',
        region_code: form.region_code, region_name: form.region_name,
        city: form.city || '-', stock: Number(form.stock),
      },
      silent: true,
    })
    uni.showToast({ title: t('上架成功'), icon: 'success' })
    setTimeout(() => navigateBack(), 800)
  } catch {
    uni.showToast({ title: t('操作失败'), icon: 'none' })
  } finally {
    submitting.value = false
  }
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--card-border); }
.form { padding: 16rpx 32rpx; margin-bottom: 24rpx; }
.field { margin-bottom: 28rpx; }
.flabel { color: var(--text-sub); font-size: 24rpx; display: block; margin-bottom: 12rpx; }
.finput { color: var(--text); font-size: 30rpx; }
.picker { color: var(--text-sub); font-size: 30rpx; }
.picker:active { opacity: 0.6; }
.tarea { width: 100%; min-height: 140rpx; color: var(--text); font-size: 28rpx; line-height: 1.5; }
.ph { color: var(--text-dim); }
.btn-primary { background: linear-gradient(135deg, var(--primary), var(--primary)); color: #fff; text-align: center; padding: 28rpx 0; border-radius: var(--radius); font-size: 30rpx; font-weight: 600; }
.btn-primary.disabled { opacity: 0.4; }
</style>
