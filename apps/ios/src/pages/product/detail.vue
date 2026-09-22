<template>
  <view class="page">
    <AppNavBar :title="t('gpuDetail')" />
    <view v-if="loading && !product" class="detail-state">{{ t('loading') }}</view>
    <view v-else-if="loadError && !product" class="detail-state detail-error">
      <text>{{ t('productLoadFailedDesc') }}</text>
      <view class="retry-button" role="button" @tap="loadProduct">{{ t('retry') }}</view>
    </view>
    <scroll-view scroll-y class="body" v-else-if="product">
      <view v-if="partialLoadError" class="partial-warning">
        <text>{{ t('partialProductDataUnavailable') }}</text>
        <text class="partial-retry" role="button" @tap="loadProduct">{{ t('retry') }}</text>
      </view>
      <image class="pimage" :src="productImageUrl" mode="aspectFill" @error="productImageFailed = true" />
      <view class="ph">
        <view class="product-heading">
          <text class="pn">{{ localizeProductName(product.name, i18n.lang) }}</text>
          <text class="seller-badge" :class="{ merchant: isMerchantProduct }">{{ t(isMerchantProduct ? 'merchantResource' : 'kaiSelfOperated') }}</text>
        </view>
        <text class="pmem">{{ product.memory }}</text>
      </view>
      <view class="card price-box">
        <template v-if="commerce.directTradeEnabled">
          <view v-if="isKaiProduct" class="price-primary">
            <text class="currency">¥</text>
            <text class="pp">{{ formatNumber(directTradeCnyPerGpuHour(product)) }}</text>
            <text class="pu">{{ t('perGpuHour') }}</text>
          </view>
          <view v-else class="price-primary">
            <text class="pp">{{ formatNumber(directTradeCardHoursPerGpuHour(product)) }}</text>
            <text class="pu">{{ t('cardHourPerGpuHour') }}</text>
          </view>
          <text v-if="isKaiProduct" class="daily muted">{{ formatNumber(directTradeCardHoursPerGpuHour(product)) }} {{ t('cardHourPerGpuHour') }}</text>
          <text v-else class="daily muted">{{ t('merchantDeclaredHourlyPrice') }}</text>
        </template>
        <template v-else-if="commerce.matchmakingEnabled && product.inquiry_available !== false">
          <text class="price-label">{{ t('servicePrice') }}</text>
          <text class="pp inquiry-price">{{ t('inquiry') }}</text>
          <text class="daily muted">{{ t('inquiryContactHint') }}</text>
        </template>
        <template v-else>
          <text class="price-label">{{ t('operationTemporarilyUnavailable') }}</text>
          <text class="pp inquiry-price unavailable-price">{{ t('viewDetail') }}</text>
          <text class="daily muted">{{ t('dataUnavailable') }}</text>
        </template>
      </view>
      <view class="card specs">
        <view class="row"><text class="sk">{{ t('gpuModel') }}</text><text class="sv">{{ product.gpu_model }}</text></view>
        <view class="row"><text class="sk">{{ t('k_224d9bc8') }}</text><text class="sv">{{ product.memory }}</text></view>
        <view class="row"><text class="sk">CUDA</text><text class="sv">{{ product.cuda || '-' }}</text></view>
        <view class="row"><text class="sk">{{ t("region") }}</text><text class="sv">{{ localizeMarketLocation(product.region_name, product.region_code, product.city, i18n.lang) || '-' }}</text></view>
        <view class="row"><text class="sk">{{ t(commerce.directTradeEnabled ? (isKaiProduct ? 'kaiFulfillmentAllocation' : 'k_40a4b798') : 'referenceAvailability') }}</text><text class="sv">{{ product.stock ?? 0 }} {{ t('units') }}</text></view>
        <view class="row"><text class="sk">{{ t('k_262a2599') }}</text><text class="sv">{{ product.stability != null ? `${formatNumber(product.stability)}%` : '-' }}</text></view>
        <view class="row"><text class="sk">{{ t('seller') }}</text><text class="sv" :class="{ 'seller-link': isMerchantProduct && product.supplier_id }" @tap="goStore">{{ sellerDisplayName }}</text></view>
        <view class="row"><text class="sk">{{ t('resourceAssurance') }}</text><text class="sv assurance-value">{{ assuranceLabel }}</text></view>
        <view class="row"><text class="sk">{{ t('deliveryMethod') }}</text><text class="sv">{{ deliveryLabel }}</text></view>
        <view v-if="product.market_source && product.market_source !== 'wod'" class="row"><text class="sk">{{ t('marketOfferSource') }}</text><text class="sv">{{ sourceName }}</text></view>
        <view v-if="product.market_source && product.market_source !== 'wod'" class="row"><text class="sk">{{ t('marketOfferUpdated') }}</text><text class="sv" :class="{ stale: !product.is_market_current }">{{ offerUpdateText }}</text></view>
        <view class="row"><text class="sk">{{ t('k_f411d0f1') }}</text><text class="sv">{{ sourceDescription }}</text></view>
      </view>

      <view v-if="!canConfigure" class="offer-warning">{{ purchaseUnavailableText }}</view>
      <view v-else class="provider-notice">{{ commerce.directTradeEnabled ? (purchaseType === 'holding' ? t('holdingDesc') : fulfillmentNotice) : t('inquiryFlowHint') }}</view>

      <SectionHeader v-if="isMerchantProduct" :title="t('sellerInformation')" />
      <view v-if="isMerchantProduct" class="card store-link" @tap="goStore">
        <view class="sl-info">
          <view class="sl-avatar">{{ sellerDisplayName.slice(0, 1).toUpperCase() }}</view>
          <view>
            <text class="sl-name">{{ sellerDisplayName }}</text>
            <text class="sl-meta">{{ sellerStats }}</text>
          </view>
        </view>
        <view v-if="product.supplier_id" class="sl-go">{{ t('进店') }} ›</view>
      </view>
      <SectionHeader v-if="isKaiProduct" :title="t('k_31f03d15')" />
      <view v-if="isKaiProduct" class="card trend-card">
        <CandlestickChart
          :candles="candles?.candles || []"
          :source-note="historySourceText"
          :history-state="chartHistoryState"
          :observed-days="chartObservedDays"
          :reference-price-cny="candles?.latest_live_price_cny ?? product.price"
          :reference-comparable-to-history="candles?.latest_live_comparable_to_history === true"
          :reference-sample-count="chartReferenceSampleCount"
          :reference-observed-at="candles?.latest_live_observed_at || product.price_updated_at || ''"
          :bucket-seconds="candles?.bucket_seconds || 0"
          range="30d"
        />
      </view>
      <SectionHeader v-if="canConfigure" :title="t(commerce.directTradeEnabled ? 'purchaseDurationHours' : 'requiredDurationHours')" />
      <view v-if="canConfigure" class="duration-card">
        <view class="duration-stepper">
          <view class="duration-button" :class="{ disabled: hours <= minPurchaseHours }" role="button" :aria-label="t('decreaseHours')" @tap="changeHours(-1)">−</view>
          <view class="duration-value-wrap">
            <input v-model.number="hours" class="duration-input" type="number" @blur="normalizeHours" />
            <text class="duration-unit">{{ t('hoursUnit') }}</text>
          </view>
          <view class="duration-button" :class="{ disabled: hours >= maxPurchaseHours }" role="button" :aria-label="t('increaseHours')" @tap="changeHours(1)">+</view>
        </view>
        <scroll-view scroll-x class="hour-presets" :show-scrollbar="false">
          <view class="hour-preset-track">
            <view v-for="value in purchaseHourOptions" :key="value" class="hour-preset" :class="{ active: hours === value }" @tap="hours = value">{{ t('hoursValue', { count: value }) }}</view>
          </view>
        </scroll-view>
        <text class="duration-hint">{{ t(commerce.directTradeEnabled ? 'hourlyBillingOnly' : 'inquiryDurationHint') }}</text>
      </view>
      <SectionHeader v-if="canConfigure" :title="t(commerce.directTradeEnabled ? 'purchaseQuantity' : 'requiredQuantity')" />
      <view v-if="canConfigure" class="quantity-row">
        <view>
          <text class="quantity-label">{{ quantityUnits(quantity) }}</text>
          <text class="quantity-stock">{{ commerce.directTradeEnabled ? t(isKaiProduct ? 'kaiAvailableAllocationHint' : 'availableQuantityHint', { count: maxQuantity }) : t('inquiryQuantityHint') }}</text>
        </view>
        <view class="quantity-stepper">
          <view class="quantity-button" :class="{ disabled: quantity <= 1 }" role="button" :aria-label="t('decreaseQuantity')" @tap="changeQuantity(-1)">−</view>
          <text class="quantity-value">{{ quantity }}</text>
          <view class="quantity-button" :class="{ disabled: quantity >= quantityLimit }" role="button" :aria-label="t('increaseQuantity')" @tap="changeQuantity(1)">+</view>
        </view>
      </view>
      <SectionHeader v-if="canConfigure" :title="t(commerce.directTradeEnabled ? 'purchaseModeLabel' : 'requirementType')" />
      <view v-if="canConfigure" class="mode-row" :class="{ dual: holdingModeAvailable }">
        <view class="mode-card" :class="{ active: purchaseType === 'usage' }" @tap="purchaseType = 'usage'">
          <template v-if="commerce.directTradeEnabled">
            <text class="mode-title">{{ t('usageMode') }}</text>
            <text class="mode-desc">{{ t('usageDesc') }}</text>
          </template>
          <template v-else>
            <text class="mode-title">{{ t('hourlyComputeRequirement') }}</text>
            <text class="mode-desc">{{ t('hourlyComputeRequirementHint') }}</text>
          </template>
        </view>
        <view v-if="commerce.directTradeEnabled && holdingModeAvailable" class="mode-card" :class="{ active: purchaseType === 'holding' }" @tap="purchaseType = 'holding'">
          <text class="mode-title">{{ t('holdingMode') }}</text>
          <text class="mode-desc">{{ t('holdingDesc') }}</text>
        </view>
      </view>
      <SectionHeader v-if="canConfigure && !commerce.directTradeEnabled" :title="t('inquirySummary')" />
      <view v-if="canConfigure" class="card fee">
        <view class="row"><text class="sk">{{ t(commerce.directTradeEnabled ? 'purchaseQuantity' : 'requiredQuantity') }}</text><text class="sv">{{ quantityUnits(quantity) }}</text></view>
        <view class="row"><text class="sk">{{ t(commerce.directTradeEnabled ? 'purchaseDurationHours' : 'requiredDurationHours') }}</text><text class="sv">{{ t('hoursValue', { count: hours }) }}</text></view>
        <view v-if="commerce.directTradeEnabled" class="row"><text class="sk">{{ t('k_a23b0e35') }}</text><text class="sv">{{ fmtCardHours(directTradeCardHoursPerGpuHour(product) * hours * quantity) }} {{ t('cardHour') }}</text></view>
        <view v-if="commerce.directTradeEnabled && purchaseType === 'usage' && rebateSummary" class="row"><text class="sk">{{ t('estimatedExpiryRebate') }}</text><text class="sv up">{{ fmtCardHours(rebateEstimate.amount) }} {{ t('cardHour') }}<template v-if="rebateEstimate.ratePercent"> · {{ rebateEstimate.ratePercent }}%</template></text></view>
        <view v-if="!commerce.directTradeEnabled" class="row"><text class="sk">{{ t('servicePrice') }}</text><text class="sv inquiry-value">{{ t('inquiry') }}</text></view>
        <view class="row"><text class="sk">{{ t('k_a46162f4') }}</text><text class="sv">{{ deliveryLabel }}</text></view>
      </view>
      <text v-if="canConfigure && commerce.directTradeEnabled && purchaseType === 'usage' && rebateSummary" class="rebate-estimate-note">{{ t('rebateEstimateCheckoutNotice') }}</text>
      <view v-if="canConfigure" class="risk">{{ t(commerce.directTradeEnabled ? (purchaseType === 'holding' ? 'holdingRisk' : 'usageRisk') : 'inquiryRiskHint') }}</view>
    </scroll-view>
    <BottomActionBar v-if="product">
      <DirectTradeProductCheckout
        v-if="commerce.directTradeEnabled"
        :product="product"
        :hours="hours"
        :quantity="quantity"
        :purchase-type="purchaseType"
        :estimated-rebate="rebateEstimate.amount"
        :estimated-rebate-rate="rebateEstimate.ratePercent"
        :disabled="!canBuy"
        :unavailable-message="purchaseUnavailableText"
      />
      <view v-else-if="commerce.matchmakingEnabled && product.inquiry_available !== false" class="buy-btn" :class="{ disabled: submitting || !canInquire }" @tap="submitInquiry">{{ t(submitting ? 'submitting' : 'submitRequirement') }}</view>
      <view v-else class="buy-btn disabled">{{ t('operationTemporarilyUnavailable') }}</view>
    </BottomActionBar>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { getProduct, type Product } from '@/api/gpu'
import type { PurchaseType } from '@/api/order'
import { getRebateSummary, type RebateSummary } from '@/api/user'
import { getMarketCandles, type MarketCandles, type MarketCandlesParams } from '@/api/market'
import { fmtCardHours, formatNumber } from '@/utils/format'
import AppNavBar from '@/components/AppNavBar.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import CandlestickChart from '@/components/CandlestickChart.vue'
import BottomActionBar from '@/components/BottomActionBar.vue'
import DirectTradeProductCheckout from '@/components/direct-trade/DirectTradeProductCheckout.vue'
import { navigateTo as nav } from '@/utils/nav'
import { useI18nStore } from '@/store/i18n'
import { useUserStore } from '@/store/user'
import { useCommerceStore } from '@/store/commerce'
import { directTradeCardHoursPerGpuHour, directTradeCnyPerGpuHour } from '@/utils/direct-trade'
import { localizeMarketLocation, productInquiryRegionRequirement } from '@/utils/region-name'
import { localizePersonName, localizeProductName } from '@/utils/localize-content'
import { fallbackProductImage, resolveProductImage } from '@/utils/product-image'
import { saveInquiryRequestPrefill } from '@/utils/inquiry-request'
import {
  historyProvenanceLabel,
  localizeMarketSourceText,
  marketHistoryDisplayState,
  marketObservedDayCount,
  marketSourceDisplayName,
} from '@/utils/market-history'
import { MARKET_PUBLICATION_MS } from '@/utils/market-polling'
import { estimateUsageExpiryRebate } from '@/utils/product-rebate'

const i18n = useI18nStore()
const { t, tr } = i18n
const userStore = useUserStore()
const commerce = useCommerceStore()
const product = ref<Awaited<ReturnType<typeof getProduct>> | null>(null)
const candles = ref<MarketCandles | null>(null)
const hours = ref(24)
const quantity = ref(1)
const purchaseType = ref<PurchaseType>('usage')
const rebateSummary = ref<RebateSummary | null>(null)
const submitting = ref(false)
const loading = ref(false)
const loadError = ref(false)
const partialLoadError = ref(false)
const productImageFailed = ref(false)
const pid = ref(0)
let candleTimer: ReturnType<typeof setInterval> | null = null
const DEFAULT_PURCHASE_HOURS = [1, 6, 12, 24, 72, 168, 360, 720]
const MAX_INQUIRY_QUANTITY = 99
const isKaiProduct = computed(() => product.value?.seller_type === 'kai_self_operated'
  || product.value?.resource_claim_source === 'kai_published'
  || product.value?.market_source === 'kai')
const isMerchantProduct = computed(() => product.value?.seller_type === 'merchant'
  || product.value?.resource_claim_source === 'merchant_declared'
  || (product.value?.market_source === 'wod' && Boolean(product.value?.supplier_id)))
const holdingModeAvailable = computed(() => isKaiProduct.value && commerce.holdingTradeEnabled)
const orderAmount = computed(() => product.value
  ? directTradeCardHoursPerGpuHour(product.value) * hours.value * quantity.value
  : 0)
const rebateEstimate = computed(() => {
  const summary = rebateSummary.value
  if (!summary) return { amount: 0, ratePercent: 0 }
  return estimateUsageExpiryRebate(
    orderAmount.value,
    purchaseType.value,
    summary.rewards_enabled,
    summary.month_spent,
    summary.minimum_order_amount,
    summary.tiers,
    summary.cap_remaining,
  )
})
const sellerDisplayName = computed(() => {
  const name = product.value?.seller_name || product.value?.supplier_name
  if (isKaiProduct.value && (!name || name === 'KAI 自营')) return t('kaiSelfOperated')
  return name ? localizePersonName(name, i18n.lang) : t('verifiedMerchant')
})
const productImageUrl = computed(() => productImageFailed.value
  ? fallbackProductImage(product.value?.gpu_model)
  : resolveProductImage(product.value?.image_url, product.value?.gpu_model))
const minPurchaseHours = computed(() => Math.max(1, Math.min(720, Math.floor(Number(product.value?.min_purchase_hours ?? 1)) || 1)))
const maxPurchaseHours = computed(() => Math.max(
  minPurchaseHours.value,
  Math.min(720, Math.floor(Number(product.value?.max_purchase_hours ?? 720)) || 720),
))
const purchaseHourOptions = computed(() => {
  const values = product.value?.purchase_hour_options || []
  return [...new Set(values.length ? values : DEFAULT_PURCHASE_HOURS)]
    .map((value) => Math.floor(Number(value)))
    .filter((value) => Number.isFinite(value) && value >= minPurchaseHours.value && value <= maxPurchaseHours.value)
    .sort((a, b) => a - b)
})
const maxQuantity = computed(() => {
  const stock = Number(product.value?.stock || 0)
  const remaining = Math.max(0, Math.floor(stock))
  if (product.value?.market_source === 'kai') {
    const sourceOrderLimit = Math.max(0, Math.floor(Number(product.value.source_max_configurable_quantity || 0)))
    return Math.min(remaining, sourceOrderLimit)
  }
  return Math.min(remaining, 99)
})
const canBuy = computed(() => Boolean(
  product.value
  && maxQuantity.value > 0
  && (
    product.value.purchasable === true
    || (purchaseType.value === 'holding' && holdingModeAvailable.value)
  ),
))
const canInquire = computed(() => Boolean(
  commerce.matchmakingEnabled
  && product.value
  && product.value.inquiry_available !== false,
))
const canConfigure = computed(() => commerce.directTradeEnabled
  ? Boolean(product.value && maxQuantity.value > 0 && (product.value.purchasable === true || holdingModeAvailable.value))
  : canInquire.value)
const quantityLimit = computed(() => commerce.directTradeEnabled ? Math.max(maxQuantity.value, 1) : MAX_INQUIRY_QUANTITY)
const purchaseUnavailableText = computed(() => {
  if (!commerce.available) return t('dataUnavailable')
  if (commerce.directTradeEnabled) {
    if (maxQuantity.value <= 0) return t(isKaiProduct.value ? 'kaiAllocationUnavailable' : 'noStockAvailable')
    if (purchaseType.value === 'holding' && holdingModeAvailable.value) return ''
    return product.value?.purchase_unavailable_reason ? tr(product.value.purchase_unavailable_reason) : t('marketOfferUnavailableShort')
  }
  return t('inquiryAvailabilityPending')
})
const sourceName = computed(() => {
  return marketSourceDisplayName(product.value?.market_source || 'wod', t)
})
const sourceDescription = computed(() => isKaiProduct.value
  ? t('kaiProductDescription')
  : localizeMarketSourceText(tr(product.value?.desc || '-'), t))
const assuranceLabel = computed(() => product.value?.assurance_label ? tr(product.value.assurance_label) : t(isMerchantProduct.value ? 'merchantDeclaredResource' : 'platformManualFulfillment'))
const deliveryLabel = computed(() => t(product.value?.fulfillment_mode === 'merchant_manual' || isMerchantProduct.value ? 'merchantManualSshDelivery' : 'platformManualSshDelivery'))
const fulfillmentNotice = computed(() => product.value?.assurance_description ? tr(product.value.assurance_description) : t(isMerchantProduct.value ? 'merchantFulfillmentNotice' : 'kaiFulfillmentAllocationNotice'))
const sellerStats = computed(() => {
  const parts = [assuranceLabel.value]
  if (product.value?.supplier_rating != null) parts.push(t('sellerRatingValue', { rating: formatNumber(product.value.supplier_rating) }))
  if (product.value?.supplier_order_count != null) parts.push(t('sellerOrderCountValue', { count: product.value.supplier_order_count }))
  return parts.join(' · ')
})
const chartHistoryState = computed(() => marketHistoryDisplayState(candles.value))
const chartObservedDays = computed(() => marketObservedDayCount(candles.value))
const chartReferenceSampleCount = computed(() => {
  const rows = candles.value?.candles || []
  return rows[rows.length - 1]?.sample_count || (product.value?.market_source ? 1 : 0)
})
const historySourceText = computed(() => historyProvenanceLabel(candles.value?.provenance, t))
function parseApiDate(value: string) {
  // SQLite/FastAPI may serialize UTC datetimes without an explicit zone.
  // Treat those values as UTC so Android/H5 do not display them eight hours
  // behind in China; preserve values that already carry Z or an offset.
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`
  return new Date(normalized)
}
const offerUpdateText = computed(() => {
  if (!product.value?.price_updated_at) return t('notUpdated')
  const formatted = parseApiDate(product.value.price_updated_at).toLocaleString(i18n.locale)
  return product.value.is_market_current ? formatted : `${formatted} · ${t(product.value.market_source_status === 'unavailable' ? 'sourceUnavailable' : 'staleData')}`
})

function productCandleParams(current: Product): MarketCandlesParams | undefined {
  if (current.market_source !== 'kai') return undefined
  const externalProductId = String(current.external_product_id || '').trim()
  return externalProductId ? { external_product_id: externalProductId } : undefined
}

onLoad((opts) => {
  pid.value = Number(opts?.id || 0)
  loadProduct()
})
onShow(() => {
  startCandleTimer()
  void refreshProductState()
  void loadRebateSummary()
})
onHide(stopCandleTimer)
onUnload(stopCandleTimer)

async function loadProduct() {
  if (loading.value) return
  if (!pid.value) {
    loadError.value = true
    return
  }
  loading.value = true
  loadError.value = false
  partialLoadError.value = false
  productImageFailed.value = false
  product.value = null
  candles.value = null

  const [productResult] = await Promise.allSettled([getProduct(pid.value)])

  if (productResult.status === 'rejected') {
    loadError.value = true
    loading.value = false
    return
  }

  product.value = productResult.value
  if (!holdingModeAvailable.value) purchaseType.value = 'usage'
  void loadRebateSummary()
  const source = product.value.market_source || 'wod'
  // Only the current KAI transport may create a live market request. Retired
  // source names remain visible on historical records without being queried.
  const candleRequest = source === 'kai'
    ? getMarketCandles(
      product.value.gpu_model,
      product.value.memory || '',
      '30d',
      [source],
      false,
      'ondemand',
      productCandleParams(product.value),
    )
    : Promise.resolve<MarketCandles | null>(null)
  const [candleResult] = await Promise.allSettled([candleRequest])
  if (candleResult.status === 'fulfilled' && candleResult.value) candles.value = candleResult.value
  partialLoadError.value = candleResult.status === 'rejected'
  if (!purchaseHourOptions.value.includes(hours.value)) {
    hours.value = purchaseHourOptions.value[0] || minPurchaseHours.value
  }
  loading.value = false
}

async function refreshProductState() {
  // Provider quotes and purchase eligibility can change while this page is
  // kept alive in the navigation stack. Refresh the product on every return so
  // an old "reference only" state cannot remain after the source recovers.
  if (!pid.value || !product.value || loading.value) return
  try {
    product.value = await getProduct(pid.value)
    if (!holdingModeAvailable.value) purchaseType.value = 'usage'
    hours.value = clampHours(hours.value)
    quantity.value = Math.min(Math.max(quantity.value, 1), quantityLimit.value)
  } catch {
    // Keep the last successfully loaded detail during a transient refresh.
  }
}

async function loadRebateSummary() {
  if (!userStore.isLogin || !commerce.directTradeEnabled) {
    rebateSummary.value = null
    return
  }
  try {
    rebateSummary.value = await getRebateSummary()
  } catch {
    rebateSummary.value = null
  }
}

async function refreshCandles(silent = true) {
  const current = product.value
  if (!current) return
  const source = current.market_source || 'wod'
  if (source !== 'kai') return
  try {
    candles.value = await getMarketCandles(
      current.gpu_model,
      current.memory || '',
      '30d',
      [source],
      silent,
      'ondemand',
      productCandleParams(current),
    )
  } catch {
    // Keep the last verified candles during a transient refresh failure.
  }
}

function startCandleTimer() {
  stopCandleTimer()
  candleTimer = setInterval(() => refreshCandles(true), MARKET_PUBLICATION_MS)
}

function stopCandleTimer() {
  if (candleTimer) clearInterval(candleTimer)
  candleTimer = null
}

function clampHours(value: number): number {
  if (!Number.isFinite(value)) return minPurchaseHours.value
  return Math.max(minPurchaseHours.value, Math.min(Math.floor(value), maxPurchaseHours.value))
}
function changeHours(delta: number) {
  hours.value = clampHours(hours.value + delta)
}
function normalizeHours() {
  hours.value = clampHours(hours.value)
}

function changeQuantity(delta: number) {
  if (!canConfigure.value) return
  quantity.value = Math.max(1, Math.min(quantity.value + delta, quantityLimit.value))
}
function quantityUnits(count: number) {
  if (i18n.lang === 'en') return `${count} ${count === 1 ? 'GPU' : 'GPUs'}`
  return t('quantityUnits', { count })
}

function submitInquiry() {
  const current = product.value
  if (submitting.value || !current || !canInquire.value) return
  submitting.value = true
  saveInquiryRequestPrefill({
    product_id: current.id,
    supplier_id: current.supplier_id,
    seller_name: sellerDisplayName.value,
    source: current.market_source || current.seller_type || 'wod',
    gpu_model: current.gpu_model,
    gpu_variant: current.memory || '',
    quantity: quantity.value,
    gpu_hours: hours.value,
    region: productInquiryRegionRequirement(current.region_name, current.region_code, current.city, i18n.lang),
    product_name: current.name,
  })
  const target = userStore.isLogin ? '/pages/buy-request/index?compose=1' : '/pages/login/index'
  nav(target)
  setTimeout(() => { submitting.value = false }, 800)
}

function goStore() {
  if (product.value?.supplier_id) {
    nav('/pages/store/index?id=' + product.value.supplier_id)
  }
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.body { flex: 1; padding: 0 32rpx 160rpx; }
.detail-state { flex: 1; min-height: 420rpx; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 24rpx; padding: 48rpx 32rpx; color: var(--text-sub); font-size: 26rpx; text-align: center; line-height: 1.6; }
.detail-error { color: var(--text-sub); }
.retry-button { min-width: 180rpx; min-height: 72rpx; display: flex; align-items: center; justify-content: center; padding: 0 28rpx; color: var(--primary); border: 1rpx solid var(--primary); border-radius: var(--radius); font-weight: 700; }
.partial-warning { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; padding: 20rpx 24rpx; margin: 24rpx 0 0; color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); font-size: 23rpx; line-height: 1.5; }
.partial-retry { flex-shrink: 0; min-height: 64rpx; display: flex; align-items: center; color: var(--primary); font-weight: 700; }
.pimage { width: 100%; height: 320rpx; background: var(--divider); border-radius: var(--radius); margin: 24rpx 0; display: block; }
.ph { display: flex; justify-content: space-between; align-items: center; gap: 20rpx; padding: 24rpx 0 32rpx; }
.product-heading { min-width: 0; display: flex; flex-direction: column; align-items: flex-start; gap: 10rpx; }
.pn { color: var(--text); font-size: 44rpx; font-weight: 700; }
.seller-badge { padding: 6rpx 14rpx; color: var(--primary); background: var(--primary-soft); border-radius: 999rpx; font-size: 20rpx; font-weight: 700; }
.seller-badge.merchant { color: var(--up); background: var(--up-soft); }
.pmem { color: var(--primary); font-size: 24rpx; background: var(--primary-soft); padding: 6rpx 18rpx; border-radius: var(--radius); }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--border); }
.trend-card { padding: 12rpx 12rpx 4rpx; overflow: hidden; }
.history-empty { padding: 72rpx 28rpx; color: var(--text-sub); font-size: 24rpx; text-align: center; }
.price-box { padding: 40rpx 32rpx; margin-bottom: 24rpx; background: var(--card); border: none; box-shadow: 0 4rpx 24rpx var(--card-border); }
.price-label { display: block; color: var(--text-sub); font-size: 23rpx; margin-bottom: 10rpx; }
.price-primary { display: flex; align-items: baseline; gap: 8rpx; }
.currency { color: var(--text-sub); font-size: 28rpx; font-weight: 700; }
.pp { color: var(--text); font-size: 56rpx; font-weight: 800; font-variant-numeric: tabular-nums; }
.inquiry-price, .inquiry-value { color: var(--primary); }
.merchant-price { color: var(--up); }
.pu { color: var(--text-sub); font-size: 26rpx; }
.daily { display: block; color: var(--up); font-size: 26rpx; margin-top: 12rpx; }
.daily.muted { color: var(--text-sub); }
.specs { padding: 8rpx 32rpx; margin-bottom: 24rpx; }
.row { display: flex; justify-content: space-between; align-items: center; padding: 28rpx 0; border-bottom: 1rpx solid var(--divider); }
.row:last-child { border-bottom: none; }
.sk { color: var(--text-sub); font-size: 28rpx; }
.sv { color: var(--text); font-size: 28rpx; font-variant-numeric: tabular-nums; }
.sv.stale { color: var(--down); }
.seller-link { color: var(--primary); }
.assurance-value { max-width: 62%; text-align: right; line-height: 1.45; }
.up { color: var(--up); }
.offer-warning { color: var(--down); background: rgba(217, 72, 72, 0.08); border: 1rpx solid rgba(217, 72, 72, 0.22); border-radius: var(--radius); padding: 20rpx 24rpx; margin-bottom: 24rpx; font-size: 24rpx; line-height: 1.5; }
.provider-notice { color: var(--text-sub); background: var(--primary-soft); border: 1rpx solid var(--card-border); border-radius: var(--radius); padding: 20rpx 24rpx; margin-bottom: 24rpx; font-size: 24rpx; line-height: 1.5; }
.duration-card { margin-bottom: 24rpx; padding: 24rpx; background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }
.duration-stepper { display: grid; grid-template-columns: 76rpx minmax(0, 1fr) 76rpx; align-items: stretch; border: 1rpx solid var(--border); border-radius: 12rpx; overflow: hidden; }
.duration-button { min-height: 76rpx; display: flex; align-items: center; justify-content: center; color: var(--primary); background: var(--primary-soft); font-size: 36rpx; font-weight: 650; }
.duration-button:active { transform: scale(0.97); }
.duration-button.disabled { color: var(--text-dim); background: var(--bg-2); }
.duration-value-wrap { min-width: 0; display: flex; align-items: center; justify-content: center; gap: 10rpx; padding: 0 16rpx; background: var(--card); }
.duration-input { width: 150rpx; height: 76rpx; color: var(--text); text-align: right; font-size: 32rpx; font-weight: 750; font-variant-numeric: tabular-nums; }
.duration-unit { color: var(--text-sub); font-size: 23rpx; }
.hour-presets { width: 100%; white-space: nowrap; margin-top: 18rpx; }
.hour-preset-track { display: inline-flex; gap: 12rpx; padding-right: 8rpx; }
.hour-preset { min-height: 58rpx; display: flex; align-items: center; justify-content: center; padding: 0 22rpx; color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: 12rpx; font-size: 22rpx; font-variant-numeric: tabular-nums; }
.hour-preset.active { color: var(--primary); background: var(--primary-soft); border-color: var(--primary); font-weight: 700; }
.duration-hint { display: block; margin-top: 16rpx; color: var(--text-sub); font-size: 21rpx; line-height: 1.5; }
.quantity-row { display: flex; align-items: center; justify-content: space-between; gap: 24rpx; padding: 22rpx 24rpx; margin-bottom: 24rpx; background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }
.quantity-label { display: block; color: var(--text); font-size: 28rpx; font-weight: 650; font-variant-numeric: tabular-nums; }
.quantity-stock { display: block; color: var(--text-sub); font-size: 21rpx; margin-top: 6rpx; }
.quantity-stepper { display: grid; grid-template-columns: 64rpx 72rpx 64rpx; align-items: center; border: 1rpx solid var(--border); border-radius: 12rpx; overflow: hidden; }
.quantity-button { height: 64rpx; display: flex; align-items: center; justify-content: center; color: var(--primary); background: var(--primary-soft); font-size: 34rpx; font-weight: 600; }
.quantity-button:active { transform: scale(0.96); }
.quantity-button.disabled { color: var(--text-dim); background: var(--bg-2); }
.quantity-value { color: var(--text); text-align: center; font-size: 28rpx; font-weight: 700; font-variant-numeric: tabular-nums; }
.mode-row { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16rpx; margin-bottom: 24rpx; }
.mode-row.dual { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.mode-card { min-width: 0; padding: 24rpx; border: 2rpx solid var(--border); border-radius: var(--radius); display: flex; flex-direction: column; gap: 8rpx; background: var(--card); }
.mode-card.active { border-color: var(--primary); background: var(--primary-soft); }
.mode-title { color: var(--text); font-size: 28rpx; font-weight: 700; }
.mode-card.active .mode-title { color: var(--primary); }
.mode-desc { color: var(--text-sub); font-size: 22rpx; line-height: 1.5; }
.fee { padding: 8rpx 32rpx; margin-bottom: 24rpx; }
.rebate-estimate-note { display: block; color: var(--text-sub); font-size: 21rpx; line-height: 1.55; padding: 0 8rpx 8rpx; }
.risk { color: var(--text-dim); font-size: 24rpx; padding: 16rpx 8rpx; line-height: 1.6; }
.buy-btn { background: var(--primary); color: #fff; text-align: center; padding: 28rpx 0; border-radius: var(--radius); font-size: 32rpx; font-weight: 600; }
.buy-btn.disabled { opacity: 0.5; }
.confirm-fee { display: flex; justify-content: space-between; align-items: center; padding: 16rpx 0; }
.cf-val { font-size: 40rpx; font-weight: 700; font-variant-numeric: tabular-nums; }

.store-link { display: flex; align-items: center; justify-content: space-between; padding: 28rpx 32rpx; margin-bottom: 24rpx; }
.sl-info { display: flex; align-items: center; gap: 20rpx; }
.sl-avatar { width: 64rpx; height: 64rpx; border-radius: 32rpx; background: linear-gradient(135deg, var(--primary), var(--primary)); color: #fff; font-size: 28rpx; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.sl-name { color: var(--text); font-size: 30rpx; font-weight: 600; }
.sl-meta { display: block; max-width: 430rpx; margin-top: 6rpx; color: var(--text-sub); font-size: 21rpx; line-height: 1.4; }
.sl-go { color: var(--primary); font-size: 26rpx; }
</style>
