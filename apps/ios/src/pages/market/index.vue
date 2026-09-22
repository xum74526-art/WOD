<template>
  <view :class="['page', pageMotionClass]">
    <view class="shell" :style="{ paddingTop: 'calc(28rpx + var(--safe-top))' }">
      <view class="title-row">
        <text class="title">{{ t("market") }}</text>
        <view class="trend-entry" @tap="nav('/pages/quote/index')"><AppIcon name="revenue" :size="30" /><text>{{ t('priceTrends') }}</text></view>
      </view>
      <view class="search">
        <AppIcon name="search" :size="36" />
        <input class="sinput" v-model="keyword" :placeholder="t('searchGPU')" placeholder-class="ph" @confirm="doSearch" />
      </view>
      <view class="source-switch" role="tablist">
        <view
          v-for="item in sourceTabs"
          :key="item.key"
          class="source-tab"
          :class="{ active: marketSource === item.key }"
          role="tab"
          :aria-selected="marketSource === item.key"
          @tap="setMarketSource(item.key)"
        >
          <text class="source-tab-title">{{ t(item.label) }}</text>
          <text class="source-tab-hint">{{ t(item.hint) }}</text>
        </view>
      </view>
      <scroll-view scroll-x class="filters" :show-scrollbar="false">
        <view v-for="item in types" :key="item.code" class="filter" :class="{ active: category === item.code }" @tap="category = item.code; load(true)">{{ t(item.name) }}</view>
      </scroll-view>
      <scroll-view scroll-x class="filters" :show-scrollbar="false">
        <view v-for="m in mems" :key="m" class="filter" :class="{ active: mem === m }" @tap="mem = m; load(true)">{{ m || t('allMemory') }}</view>
      </scroll-view>
      <scroll-view scroll-x class="filters" :show-scrollbar="false">
        <view v-for="r in regions" :key="r.code" class="filter" :class="{ active: region === r.code }" @tap="region = r.code; load(true)">{{ t(r.name) }}</view>
      </scroll-view>
      <view class="sortbar">
        <view v-for="s in sorts" :key="s.key" class="sort" :class="{ active: sort === s.key }" @tap="sort = s.key; load(true)">{{ t(s.label) }}</view>
      </view>
      <view v-if="loading && !list.length" class="state">{{ t("loading") }}</view>
      <view v-else-if="loadError && !list.length" class="state error-state">
        <text>{{ t('dataUnavailable') }}</text>
        <view class="retry-button" role="button" @tap="load(true)">{{ t('retry') }}</view>
      </view>
      <view v-else-if="!list.length" class="state">{{ t(marketSource === 'kai' ? 'noKaiListings' : 'noMerchantListings') }}</view>
      <view v-for="p in list" :key="p.id" class="card prod pressable" @tap="go(p.id)">
        <image
          class="pimg"
          :src="productImage(p)"
          mode="aspectFill"
          lazy-load
          :fade-show="false"
          @error="markImageFailed(p.id)"
        />
        <view class="pbody">
          <view class="seller-line">
            <text class="seller-badge" :class="{ merchant: isMerchantProduct(p) }">{{ t(isMerchantProduct(p) ? 'merchantResource' : 'kaiSelfOperated') }}</text>
            <text class="seller-assurance">{{ assuranceText(p) }}</text>
          </view>
          <view class="pt">
            <text class="pn">{{ localizeProductName(p.name, i18n.lang) }}</text>
            <text class="pmem">{{ p.memory }}</text>
          </view>
          <view class="pmid">
            <view class="info"><text class="il">{{ t(commerce.directTradeEnabled ? (isKaiProduct(p) ? 'kaiFulfillmentAllocation' : 'availableQuantity') : 'referenceAvailability') }}</text><text class="iv">{{ p.stock ?? 0 }}</text></view>
            <view class="info"><text class="il">{{ t("region") }}</text><text class="iv">{{ localizeRegionName(p.region_name || '-', i18n.lang, p.region_code) }}</text></view>
            <view class="info">
              <text class="il">{{ t('seller') }}</text>
              <text class="iv" :class="{ 'info-link': p.supplier_id }" @tap.stop="goStore(p.supplier_id)">{{ sellerName(p) }}</text>
            </view>
          </view>
          <view class="pbot">
            <view class="pprice">
              <template v-if="commerce.directTradeEnabled">
                <view class="hourly-price"><text class="pp">{{ formatAmount(directTradeCardHoursPerGpuHour(p)) }}</text><text class="pu">{{ t('cardHourPerGpuHour') }}</text></view>
                <text v-if="isKaiProduct(p)" class="price-cny">¥{{ formatAmount(directTradeCnyPerGpuHour(p)) }}{{ t('perGpuHour') }}</text>
              </template>
              <template v-else-if="commerce.matchmakingEnabled && p.inquiry_available !== false">
                <view class="hourly-price"><text class="pp">{{ t('inquiry') }}</text></view>
                <text class="price-cny">{{ t('inquiryContactHintShort') }}</text>
              </template>
              <template v-else>
                <view class="hourly-price"><text class="pp unavailable-price">{{ t('viewDetail') }}</text></view>
                <text class="price-cny">{{ t('operationTemporarilyUnavailable') }}</text>
              </template>
              <view v-if="isKaiProduct(p)" class="market-card-metrics">
                <text class="pch" :class="changeTone(modelChange(p))">{{ modelChangeText(p) }}</text>
                <text class="pch-range">{{ modelPriceRangeText(p) }}</text>
                <text v-if="modelHistorySourceText(p)" class="pch-source">{{ modelHistorySourceText(p) }}</text>
              </view>
              <text v-else class="merchant-meta">{{ merchantMeta(p) }}</text>
            </view>
            <view v-if="commerce.directTradeEnabled" class="buy" :class="{ disabled: !directTradeProductPurchasable(p) }">{{ t(directTradeProductPurchasable(p) ? 'k_25575fc0' : 'viewDetail') }}</view>
            <view v-else-if="commerce.matchmakingEnabled && p.inquiry_available !== false" class="buy">{{ t('submitRequirement') }}</view>
            <view v-else class="buy disabled">{{ t('viewDetail') }}</view>
          </view>
        </view>
      </view>
      <view v-if="loading && list.length" class="state">{{ t('loadMore') }}</view>
      <view v-if="finished && list.length" class="state">{{ t('共 {count} 个算力资源，已全部加载', { count: total }) }}</view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onShow, onReachBottom } from '@dcloudio/uni-app'
import { getProducts } from '@/api/gpu'
import { getMarketRanking, type MarketRankingItem } from '@/api/market'
import type { Product } from '@/api/gpu'
import AppIcon from '@/components/AppIcon.vue'
import { navigateTo as nav } from '@/utils/nav'
import { usePageMotion } from '@/utils/page-motion'
import { fmtCHn, formatAmount, formatNumber } from '@/utils/format'
import { directTradeCardHoursPerGpuHour, directTradeCnyPerGpuHour, directTradeProductPurchasable } from '@/utils/direct-trade'
import { useI18nStore } from '@/store/i18n'
import { useCommerceStore } from '@/store/commerce'
import { localizePersonName, localizeProductName } from '@/utils/localize-content'
import { localizeRegionName } from '@/utils/region-name'
import { formatSignedMarketPercentNumber } from '@/utils/market-chart'
import { marketSourceDisplayName } from '@/utils/market-history'
import { MARKET_PUBLICATION_MS } from '@/utils/market-polling'
import { fallbackProductImage, resolveProductImage } from '@/utils/product-image'
import {
  buildMarketRangeMap,
  gpuMarketKey,
  hasCompleteSevenDayMetric,
  mergeUniqueProducts,
  sortByMarketPriority,
  trustedSevenDayChange,
  trustedSevenDayPriceRange,
  type MarketRangeMap,
} from '@/utils/market-list'

const i18n = useI18nStore()
const { pageMotionClass } = usePageMotion()
const { t, tr } = i18n
const commerce = useCommerceStore()
const list = ref<Product[]>([])
const loading = ref(false)
const loadError = ref(false)
const finished = ref(false)
const total = ref(0)
const page = ref(1)
const keyword = ref('')
const mem = ref('')
const region = ref('')
const category = ref('')
const sort = ref('default')
type MarketSourceFilter = 'kai' | 'wod'
const marketSource = ref<MarketSourceFilter>('kai')
type ModelRange = Pick<MarketRankingItem, 'change_7d_pct' | 'range_low_cny' | 'range_high_cny' | 'history_day_count' | 'history_span_hours' | 'market_status' | 'history_provenance'>
const volatilityMap = ref<MarketRangeMap & Record<string, ModelRange>>({})
const failedImages = ref<Record<number, boolean>>({})
let quoteLoadedAt = 0
let quoteInFlight: Promise<void> | null = null
let loadGeneration = 0
let productsLoadedAt = 0

const sourceTabs: Array<{ key: MarketSourceFilter; label: string; hint: string }> = [
  { key: 'kai', label: 'kaiSelfOperated', hint: 'kaiSelfOperatedHint' },
  { key: 'wod', label: 'merchantResources', hint: 'merchantResourcesHint' },
]

async function loadQuote() {
  if (Date.now() - quoteLoadedAt < MARKET_PUBLICATION_MS) return
  if (quoteInFlight) return quoteInFlight
  quoteInFlight = (async () => {
    try {
      const ranking = await getMarketRanking(true)
      volatilityMap.value = buildMarketRangeMap(ranking.items.filter((item) => item.sources.includes('kai'))) as MarketRangeMap & Record<string, ModelRange>
      quoteLoadedAt = Date.now()
      if (marketSource.value === 'kai' && sort.value === 'default' && list.value.length) {
        list.value = sortByMarketPriority(list.value, volatilityMap.value)
      }
    } catch {
      // 商品列表不依赖行情接口；行情暂不可用时仍优先展示可租资源。
    } finally {
      quoteInFlight = null
    }
  })()
  return quoteInFlight
}

const types = [
  { code: '', name: 'allTypes' },
  { code: 'h_series', name: 'hSeries' },
  { code: 'a_series', name: 'aSeries' },
  { code: 'consumer', name: 'consumer' },
  { code: 'professional', name: 'professional' },
  { code: 'domestic', name: 'domestic' },
  { code: 'vgpu', name: 'vgpu' },
]
const mems = ['', '80GB', '48GB', '40GB', '24GB', '16GB']
const regions = [
  { code: '', name: 'allRegions' },
  { code: 'north_china', name: 'northChina' },
  { code: 'east_china', name: 'eastChina' },
  { code: 'south_china', name: 'southChina' },
  { code: 'northwest_china', name: 'northwest' },
  { code: 'southwest_china', name: 'southwest' },
]
const sorts = computed(() => commerce.directTradeEnabled
  ? [
      { key: 'default', label: 'hotSort' },
      { key: 'price_asc', label: 'sortPriceUp' },
      { key: 'price_desc', label: 'sortPriceDown' },
    ]
  : [{ key: 'default', label: 'hotSort' }])

async function load(reset = false) {
  if (!reset && (loading.value || finished.value)) return
  if (reset) {
    loadGeneration++
    page.value = 1
    list.value = []
    loadError.value = false
    finished.value = false
  }
  const generation = loadGeneration
  const requestedPage = page.value
  loading.value = true
  try {
    const res = await getProducts({
      keyword: keyword.value || undefined,
      memory: mem.value || undefined,
      region: region.value || undefined,
      category: category.value || undefined,
      sort: sort.value,
      page: requestedPage,
      page_size: 100,
       market_source: marketSource.value,
       representative: marketSource.value === 'kai',
     })
     if (generation !== loadGeneration) return
     const sourceItems = res.items.filter((item) => item.market_source === marketSource.value)
     list.value = requestedPage === 1 ? sourceItems : mergeUniqueProducts(list.value, sourceItems)
     if (marketSource.value === 'kai' && sort.value === 'default') list.value = sortByMarketPriority(list.value, volatilityMap.value)
    total.value = res.total
    if (requestedPage === 1) productsLoadedAt = Date.now()
    if (list.value.length >= res.total) finished.value = true
    else page.value = requestedPage + 1
  } catch {
    // request.ts 已负责向用户提示网络错误。
    if (generation === loadGeneration && requestedPage === 1) loadError.value = true
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

onShow(() => {
  i18n.updateTabBar()
  const storedKeyword = uni.getStorageSync('wod-market-keyword')
  let shouldReload = !list.value.length || Date.now() - productsLoadedAt >= MARKET_PUBLICATION_MS
  if (!commerce.directTradeEnabled && sort.value !== 'default') {
    sort.value = 'default'
    shouldReload = true
  }
  if (storedKeyword) {
    keyword.value = String(storedKeyword)
    uni.removeStorageSync('wod-market-keyword')
    shouldReload = true
  }
  // 商品和行情并行加载。首屏不再被耗时较长的行情统计接口阻塞。
  if (shouldReload) void load(true)
  void loadQuote()
})
onReachBottom(() => load())
function doSearch() { load(true) }
function setMarketSource(source: MarketSourceFilter) {
  if (marketSource.value === source) return
  marketSource.value = source
  load(true)
}
function go(id: number) { nav('/pages/product/detail?id=' + id) }
function goStore(sid?: number | null) { if (sid) nav('/pages/store/index?id=' + sid) }
function isMerchantProduct(product: Pick<Product, 'market_source' | 'seller_type' | 'supplier_id' | 'resource_claim_source'>): boolean {
  return product.seller_type === 'merchant'
    || product.resource_claim_source === 'merchant_declared'
    || (product.market_source === 'wod' && Boolean(product.supplier_id))
}
function isKaiProduct(product: Pick<Product, 'market_source' | 'seller_type' | 'resource_claim_source'>): boolean {
  return product.seller_type === 'kai_self_operated'
    || product.resource_claim_source === 'kai_published'
    || product.market_source === 'kai'
}
function sellerName(product: Pick<Product, 'market_source' | 'seller_type' | 'supplier_id' | 'resource_claim_source' | 'seller_name' | 'supplier_name'>) {
  const name = product.seller_name || product.supplier_name
  if (isKaiProduct(product) && (!name || name === 'KAI 自营')) return t('kaiSelfOperated')
  return name ? localizePersonName(name, i18n.lang) : t('verifiedMerchant')
}
function assuranceText(product: Pick<Product, 'market_source' | 'seller_type' | 'supplier_id' | 'resource_claim_source' | 'assurance_label'>) {
  return product.assurance_label ? tr(product.assurance_label) : t(isMerchantProduct(product) ? 'merchantDeclaredResource' : 'platformManualFulfillment')
}
function merchantMeta(product: Pick<Product, 'supplier_rating' | 'supplier_order_count' | 'fulfillment_mode'>) {
  const parts = [t(product.fulfillment_mode === 'platform_manual' ? 'platformManualFulfillment' : 'merchantManualFulfillment')]
  if (product.supplier_rating != null) parts.push(t('sellerRatingValue', { rating: formatNumber(product.supplier_rating) }))
  if (product.supplier_order_count != null) parts.push(t('sellerOrderCountValue', { count: product.supplier_order_count }))
  return parts.join(' · ')
}
function modelRange(p: Pick<Product, 'gpu_model' | 'memory'>): ModelRange | undefined { return volatilityMap.value[gpuMarketKey(p.gpu_model, p.memory)] }
function modelChange(p: Pick<Product, 'gpu_model' | 'memory'>): number | null {
  const metric = modelRange(p)
  return hasCompleteSevenDayMetric(metric) ? trustedSevenDayChange(metric) : null
}
function modelChangeText(p: Pick<Product, 'gpu_model' | 'memory'>): string {
  const value = modelChange(p)
  const metric = modelRange(p)
  return value == null
    ? (Number(metric?.history_day_count || 0) > 1 ? t('chartObservedDays', { days: metric!.history_day_count }) : t('currentQuoteBaseline'))
    : t('sevenDayChangeValue', { value: formatSignedMarketPercentNumber(value) })
}
function modelPriceRangeText(p: Pick<Product, 'gpu_model' | 'memory'>): string {
  const metric = modelRange(p)
  const range = hasCompleteSevenDayMetric(metric) ? trustedSevenDayPriceRange(metric) : null
  return range
    ? t('sevenDayPriceRangeValue', { low: fmtCHn(range.low), high: fmtCHn(range.high) })
    : (Number(metric?.history_day_count || 0) > 1 ? t('chartObservedDays', { days: metric!.history_day_count }) : t('currentQuoteBaseline'))
}
function modelHistorySourceText(p: Pick<Product, 'gpu_model' | 'memory'>): string {
  const provenance = modelRange(p)?.history_provenance
  const provider = String(provenance?.upstream_provider || '').trim()
  if (!provider) return ''
  const providerName = marketSourceDisplayName(provider, t)
  return provenance?.kind === 'external_reference'
    ? t('historyReferenceProviderShort', { provider: providerName })
    : t('historyObservedProviderShort', { provider: providerName })
}
function changeTone(value: number | null): string {
  return value == null || value === 0 ? 'neutral' : value > 0 ? 'rise' : 'fall'
}
function productImage(p: Pick<Product, 'id' | 'image_url' | 'gpu_model'>): string {
  if (failedImages.value[p.id]) return fallbackProductImage(p.gpu_model)
  return resolveProductImage(p.image_url, p.gpu_model)
}
function markImageFailed(id: number) {
  if (!failedImages.value[id]) failedImages.value = { ...failedImages.value, [id]: true }
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.title-row { position: relative; z-index: 2; display: flex; align-items: center; justify-content: space-between; min-height: 88rpx; margin: 16rpx 0 24rpx; }
.title { display: block; color: var(--text); font-size: 44rpx; font-weight: 700; }
.trend-entry { min-height: 88rpx; display: flex; align-items: center; gap: 8rpx; color: var(--primary); font-size: 23rpx; padding: 12rpx 18rpx; border: 1rpx solid var(--primary); border-radius: 12rpx; }
.search { display: flex; align-items: center; background: var(--card); border: 1rpx solid var(--primary-soft); border-radius: var(--radius); padding: 0 24rpx; margin-bottom: 20rpx; }
.sinput { flex: 1; color: var(--text); font-size: 28rpx; height: 80rpx; margin-left: 16rpx; }
.ph { color: var(--text-dim); }
.source-switch { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16rpx; margin-bottom: 20rpx; }
.source-tab { min-width: 0; padding: 18rpx 20rpx; color: var(--text-sub); background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }
.source-tab.active { color: var(--primary); background: var(--primary-soft); border-color: var(--primary); }
.source-tab-title { display: block; font-size: 27rpx; font-weight: 700; }
.source-tab-hint { display: block; margin-top: 4rpx; font-size: 19rpx; line-height: 1.35; }
.filters { white-space: nowrap; margin-bottom: 16rpx; }
.filter { min-height: 72rpx; display: inline-flex; align-items: center; padding: 10rpx 28rpx; margin-right: 16rpx; background: var(--card); border-radius: var(--radius); color: var(--text-sub); font-size: 24rpx; border: 1rpx solid var(--primary-soft); }
.filter.active { background: var(--card-border); color: var(--primary); border-color: transparent; }
.sortbar { display: flex; gap: 32rpx; margin-bottom: 24rpx; }
.sort { min-height: 72rpx; display: flex; align-items: center; color: var(--text-sub); font-size: 26rpx; padding: 8rpx 0; }
.sort.active { color: var(--text); font-weight: 600; position: relative; }
.sort.active::after { content: ''; position: absolute; left: 0; right: 0; bottom: 0; height: 4rpx; background: var(--primary); border-radius: 2rpx; }
.state { color: var(--text-sub); text-align: center; padding: 40rpx 0; font-size: 26rpx; }
.error-state { display: flex; flex-direction: column; align-items: center; gap: 20rpx; }
.retry-button { min-height: 72rpx; padding: 0 32rpx; display: flex; align-items: center; justify-content: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: var(--radius); font-weight: 600; }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--card-border); box-shadow: 0 4rpx 24rpx var(--card-border); }
.prod { overflow: hidden; margin-bottom: 24rpx; }
.pimg { width: 100%; height: 240rpx; display: block; }
.pbody { padding: 32rpx; }
.seller-line { display: flex; align-items: center; justify-content: space-between; gap: 16rpx; margin-bottom: 18rpx; }
.seller-badge { flex-shrink: 0; padding: 6rpx 14rpx; color: var(--primary); background: var(--primary-soft); border-radius: 999rpx; font-size: 20rpx; font-weight: 700; }
.seller-badge.merchant { color: var(--up); background: var(--up-soft); }
.seller-assurance { min-width: 0; color: var(--text-dim); font-size: 19rpx; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pt { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24rpx; }
.pn { color: var(--text); font-size: 34rpx; font-weight: 600; }
.pmem { color: var(--primary); font-size: 24rpx; background: rgba(24,175,196,0.14); padding: 6rpx 18rpx; border-radius: 10rpx; }
.pmid { display: flex; justify-content: space-between; padding: 24rpx 0; border-top: 1rpx solid var(--divider); border-bottom: 1rpx solid var(--divider); margin-bottom: 24rpx; }
.info { display: flex; flex-direction: column; align-items: center; }
.il { color: var(--text-sub); font-size: 22rpx; }
.iv { color: var(--text); font-size: 28rpx; font-weight: 600; margin-top: 8rpx; font-variant-numeric: tabular-nums; }
.info-link { color: var(--primary); }
.up { color: var(--up); }
.pprice { min-width: 0; flex: 1; display: flex; flex-direction: column; align-items: flex-start; gap: 10rpx; }
.hourly-price { display: flex; align-items: baseline; gap: 8rpx; }
.price-cny { color: var(--text-dim); font-size: 19rpx; font-variant-numeric: tabular-nums; }
.market-card-metrics { display: flex; flex-direction: column; align-items: flex-start; gap: 6rpx; }
.pch { color: var(--primary); background: var(--primary-soft); font-size: 22rpx; font-weight: 600; padding: 4rpx 12rpx; border-radius: 8rpx; }
.pch.rise { color: #C9363E; background: rgba(229,72,77,0.1); }
.pch.fall { color: #168A5B; background: rgba(22,163,106,0.1); }
.pch.neutral { color: var(--text-sub); background: var(--bg-2); }
.pch-range { color: var(--text-sub); font-size: 20rpx; line-height: 1.35; font-variant-numeric: tabular-nums; }
.pch-source { color: var(--text-dim); font-size: 18rpx; line-height: 1.3; }
.merchant-meta { color: var(--text-sub); font-size: 20rpx; line-height: 1.4; }
.pbot { display: flex; justify-content: space-between; align-items: flex-end; gap: 18rpx; }
.pp { color: var(--up); font-size: 40rpx; font-weight: 700; font-variant-numeric: tabular-nums; }
.pu { color: var(--text-sub); font-size: 24rpx; }
.buy { color: var(--primary); font-size: 26rpx; border: 1rpx solid var(--primary); padding: 12rpx 32rpx; border-radius: var(--radius); }
.buy.disabled { color: var(--text-dim); border-color: var(--border); }
</style>
