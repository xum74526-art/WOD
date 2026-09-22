<template>
  <view class="page">
    <AppNavBar :title="t('k_f258ae4c')" />
    <view class="shell">
      <view v-if="loading" class="state">{{ t('loading') }}</view>
      <view v-else-if="loadError" class="load-error">
        <text>{{ t('supplierLoadFailedDesc') }}</text>
        <text class="load-retry" role="button" @tap="load">{{ t('retry') }}</text>
      </view>
      <template v-else-if="info">
        <view class="card store-card">
          <view class="sc-row">
            <view class="sc-avatar">{{ displayCompanyName.slice(0, 1).toUpperCase() || t('商') }}</view>
            <view class="sc-info">
              <text class="sc-name">{{ displayCompanyName }}</text>
              <text v-if="contactSummary" class="sc-sub">{{ contactSummary }}</text>
      <text class="sc-tags">{{ localizeRegionName(info.region || '', i18n.lang) }} · {{ t('评分 {rating}', { rating: info.rating == null ? '-' : formatNumber(info.rating) }) }} · {{ t('{count} 单', { count: info.order_count ?? 0 }) }}</text>
            </view>
          </view>
          <text class="sc-desc" v-if="info.desc">{{ tr(info.desc) }}</text>
        </view>

        <SectionHeader :title="t('k_35c97a9a')" />
        <view v-if="!products.length" class="card ph"><EmptyState text="暂无在售商品" /></view>
        <view v-for="p in products" :key="p.id" class="card prod" @tap="goDetail(p.id)">
          <image class="pimg" :src="productImage(p)" mode="aspectFill" lazy-load :fade-show="false" @error="markImageFailed(p.id)" />
          <view class="pbody">
            <view class="pt"><text class="pn">{{ localizeProductName(p.name, i18n.lang) }}</text><text class="pmem">{{ p.memory }}</text></view>
            <view class="pbot">
              <template v-if="commerce.directTradeEnabled">
                <text class="pp">{{ formatAmount(directTradeCardHoursPerGpuHour(p)) }}</text>
                <text class="pu">{{ t('cardHourPerGpuHour') }}</text>
              </template>
              <text v-else-if="commerce.matchmakingEnabled && p.inquiry_available !== false" class="pp">{{ t('inquiry') }}</text>
              <text v-else class="pp unavailable">{{ t('dataUnavailable') }}</text>
              <text class="pstock">{{ t('rentable') }} {{ p.stock }}</text>
              <text v-if="commerce.directTradeEnabled" class="p-buy">{{ t(directTradeProductPurchasable(p) ? 'k_25575fc0' : 'viewDetail') }}</text>
              <text v-else-if="commerce.matchmakingEnabled && p.inquiry_available !== false" class="p-buy">{{ t('submitRequirement') }}</text>
              <text v-else class="p-buy disabled">{{ t('viewDetail') }}</text>
            </view>
          </view>
        </view>

        <view v-if="hasPhone" class="contact-btn" @tap="contactSupplier">{{ t('k_ad214772') }}</view>
      </template>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getStore, type SupplierInfo } from '@/api/supplier'
import type { Product } from '@/api/gpu'
import AppNavBar from '@/components/AppNavBar.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import { navigateTo as nav } from '@/utils/nav'
import { formatAmount, formatNumber } from '@/utils/format'
import { useI18nStore } from '@/store/i18n'
import { useCommerceStore } from '@/store/commerce'
import { localizePersonName, localizeProductName } from '@/utils/localize-content'
import { localizeRegionName } from '@/utils/region-name'
import { fallbackProductImage, resolveProductImage } from '@/utils/product-image'
import { directTradeCardHoursPerGpuHour, directTradeProductPurchasable } from '@/utils/direct-trade'

const i18n = useI18nStore()
const commerce = useCommerceStore()
const { t, tr } = i18n
const info = ref<SupplierInfo | null>(null)
const products = ref<Product[]>([])
const sid = ref(0)
const loading = ref(false)
const loadError = ref(false)
const failedImages = ref<Record<number, boolean>>({})
const displayCompanyName = computed(() => localizePersonName(info.value?.company_name || '', i18n.lang))
const displayContactName = computed(() => localizePersonName(info.value?.contact || '', i18n.lang))
const hasPhone = computed(() => Boolean(info.value?.phone?.trim()))
const contactSummary = computed(() => [displayContactName.value, info.value?.phone?.trim()].filter(Boolean).join(' · '))

onLoad((opts) => {
  sid.value = Number(opts?.id || 0)
  if (!sid.value) {
    loadError.value = true
    return
  }
  load()
})

async function load() {
  if (loading.value || !sid.value) return
  loading.value = true
  loadError.value = false
  try {
    const d = await getStore(sid.value)
    info.value = d.supplier
    products.value = d.products
  } catch {
    info.value = null
    products.value = []
    loadError.value = true
  } finally {
    loading.value = false
  }
}

function goDetail(id: number) { nav('/pages/product/detail?id=' + id) }
function productImage(product: Pick<Product, 'id' | 'image_url' | 'gpu_model'>) {
  return failedImages.value[product.id]
    ? fallbackProductImage(product.gpu_model)
    : resolveProductImage(product.image_url, product.gpu_model)
}
function markImageFailed(id: number) {
  if (!failedImages.value[id]) failedImages.value = { ...failedImages.value, [id]: true }
}
function contactSupplier() {
  const phone = info.value?.phone?.trim()
  if (!phone) return
  const lines = [
    displayCompanyName.value,
    displayContactName.value ? `${t('k_52409da5')}: ${displayContactName.value}` : '',
    `${t('电话')}: ${phone}`,
  ].filter(Boolean)
  uni.showModal({
    title: t('k_ad214772'),
    content: lines.join('\n'),
    confirmText: t('复制电话'),
    success: (r) => {
      if (r.confirm) uni.setClipboardData({ data: phone })
    },
  })
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.state { min-height: 360rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 26rpx; }
.load-error { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; padding: 20rpx 24rpx; margin: 24rpx 0; color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); font-size: 23rpx; line-height: 1.5; }
.load-retry { flex-shrink: 0; min-height: 64rpx; display: flex; align-items: center; color: var(--primary); font-weight: 700; }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--card-border); }
.store-card { padding: 36rpx 32rpx; margin: 24rpx 0; }
.sc-row { display: flex; align-items: center; }
.sc-avatar { width: 96rpx; height: 96rpx; border-radius: 48rpx; background: linear-gradient(135deg, var(--primary), var(--primary)); color: #fff; font-size: 40rpx; font-weight: 700; display: flex; align-items: center; justify-content: center; margin-right: 28rpx; }
.sc-info { flex: 1; }
.sc-name { color: var(--text); font-size: 34rpx; font-weight: 700; display: block; }
.sc-sub { color: var(--text-sub); font-size: 24rpx; margin-top: 8rpx; display: block; }
.sc-tags { color: var(--primary); font-size: 22rpx; margin-top: 8rpx; display: block; }
.sc-desc { display: block; color: var(--text-sub); font-size: 26rpx; margin-top: 24rpx; padding-top: 24rpx; border-top: 1rpx solid var(--divider); line-height: 1.6; }
.ph { padding: 60rpx 0; }
.prod { overflow: hidden; margin-bottom: 20rpx; }
.pimg { width: 100%; height: 220rpx; display: block; }
.pbody { padding: 28rpx 32rpx; }
.pt { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20rpx; }
.pn { color: var(--text); font-size: 32rpx; font-weight: 600; }
.pmem { color: var(--primary); font-size: 22rpx; background: var(--card-border); padding: 4rpx 16rpx; border-radius: 8rpx; }
.pbot { display: flex; align-items: baseline; gap: 12rpx; flex-wrap: wrap; }
.pp { color: var(--up); font-size: 36rpx; font-weight: 700; font-variant-numeric: tabular-nums; }
.pu { color: var(--text-sub); font-size: 22rpx; }
.pstock { color: var(--text-sub); font-size: 22rpx; margin-left: auto; }
.p-buy { flex-basis: 100%; margin-top: 10rpx; color: var(--primary); font-size: 24rpx; text-align: right; }
.p-buy.disabled { color: var(--text-dim); }
.contact-btn { text-align: center; padding: 28rpx; border: 1rpx solid var(--primary); color: var(--primary); border-radius: var(--radius); font-size: 28rpx; margin-top: 24rpx; }
</style>
