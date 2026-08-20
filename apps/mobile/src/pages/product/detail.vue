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
        <text class="pn">{{ localizeProductName(product.name, i18n.lang) }}</text>
        <text class="pmem">{{ product.memory }}</text>
      </view>
      <view class="card price-box">
        <view><text class="pp">{{ fmtCH(product.price) }}</text><text class="pu">/h</text></view>
        <text class="daily muted">{{ t('revenueDataUnavailable') }}</text>
      </view>
      <view class="card specs">
        <view class="row"><text class="sk">{{ t('gpuModel') }}</text><text class="sv">{{ product.gpu_model }}</text></view>
        <view class="row"><text class="sk">{{ t('k_224d9bc8') }}</text><text class="sv">{{ product.memory }}</text></view>
        <view class="row"><text class="sk">CUDA</text><text class="sv">{{ product.cuda || '-' }}</text></view>
        <view class="row"><text class="sk">{{ t("region") }}</text><text class="sv">{{ tr(product.region_name || '-') }} {{ localizeRegionName(product.city || '', i18n.lang) }}</text></view>
        <view class="row"><text class="sk">{{ t('k_40a4b798') }}</text><text class="sv">{{ product.stock }} {{ t('units') }}</text></view>
        <view class="row"><text class="sk">{{ t('k_262a2599') }}</text><text class="sv">{{ product.stability != null ? `${formatNumber(product.stability)}%` : '-' }}</text></view>
        <view v-if="product.market_source && product.market_source !== 'wod'" class="row"><text class="sk">{{ t('marketOfferSource') }}</text><text class="sv">{{ sourceName }}</text></view>
        <view v-if="product.market_source && product.market_source !== 'wod'" class="row"><text class="sk">{{ t('marketOfferUpdated') }}</text><text class="sv" :class="{ stale: !product.is_market_current }">{{ offerUpdateText }}</text></view>
        <view class="row"><text class="sk">{{ t('k_f411d0f1') }}</text><text class="sv">{{ tr(product.desc || '-') }}</text></view>
      </view>

      <view v-if="!canBuy" class="offer-warning">{{ purchaseUnavailableText }}</view>
      <view v-else-if="isProviderOffer" class="provider-notice">{{ t('providerFulfillmentNotice') }}</view>

      <SectionHeader v-if="product.supplier_name" :title="t('k_bab268d5')" />
      <view v-if="product.supplier_name" class="card store-link" @tap="goStore">
        <view class="sl-info">
          <view class="sl-avatar">{{ supplierName.slice(0, 1).toUpperCase() }}</view>
          <text class="sl-name">{{ supplierName }}</text>
        </view>
        <view class="sl-go">{{ t('进店') }} ›</view>
      </view>
      <SectionHeader :title="t('k_31f03d15')" />
      <view class="card trend-card">
        <CandlestickChart
          :candles="candles?.candles || []"
          :source-note="historySourceText"
          :history-state="chartHistoryState"
          :observed-days="chartObservedDays"
          :reference-price-cny="candles?.latest_live_price_cny ?? product.price"
          :reference-sample-count="chartReferenceSampleCount"
          :reference-observed-at="candles?.latest_live_observed_at || product.price_updated_at || ''"
        />
      </view>
      <SectionHeader v-if="canBuy" :title="t('k_080aeb64')" />
      <view v-if="canBuy" class="cycles">
        <view v-for="c in purchaseCycles" :key="c" class="cycle" :class="{ active: cycle === c }" @tap="cycle = c">{{ cycleLabel(c) }}</view>
      </view>
      <SectionHeader v-if="canBuy" :title="t('purchaseQuantity')" />
      <view v-if="canBuy" class="quantity-row">
        <view>
          <text class="quantity-label">{{ quantityUnits(quantity) }}</text>
          <text class="quantity-stock">{{ t('availableQuantityHint', { count: maxQuantity }) }}</text>
        </view>
        <view class="quantity-stepper">
          <view class="quantity-button" :class="{ disabled: quantity <= 1 }" role="button" :aria-label="t('decreaseQuantity')" @tap="changeQuantity(-1)">−</view>
          <text class="quantity-value">{{ quantity }}</text>
          <view class="quantity-button" :class="{ disabled: quantity >= maxQuantity }" role="button" :aria-label="t('increaseQuantity')" @tap="changeQuantity(1)">+</view>
        </view>
      </view>
      <SectionHeader v-if="canBuy" :title="t('k_21c8bb00')" />
      <view v-if="canBuy" class="mode-row">
        <view class="mode-card" :class="{ active: purchaseType === 'usage' }" @tap="purchaseType = 'usage'">
          <text class="mode-title">{{ t('k_25575fc0') }}</text>
          <text class="mode-desc">{{ t('k_fb271ebb') }}</text>
        </view>
        <view class="mode-card" :class="{ active: purchaseType === 'holding' }" @tap="purchaseType = 'holding'">
          <text class="mode-title">{{ t('holdingMode') }}</text>
          <text class="mode-desc">{{ t('holdingDesc') }}</text>
        </view>
      </view>
      <view v-if="canBuy" class="card fee">
        <view class="row"><text class="sk">{{ t('purchaseQuantity') }}</text><text class="sv">{{ quantityUnits(quantity) }}</text></view>
        <view class="row"><text class="sk">{{ t('k_a23b0e35') }}</text><text class="sv">{{ fmtCH(amount) }}</text></view>
        <view class="row"><text class="sk">{{ t('k_a46162f4') }}</text><text class="sv">{{ t('sshDelivery') }}</text></view>
        <view class="row" v-if="rebate && estRebate > 0"><text class="sk">{{ t('k_64913945') }}</text><text class="sv up">+{{ fmtCardHours(estRebate) }} {{ t('cardHour') }} ({{ formatNumber(estRebateRate) }}%)</text></view>
        <view class="row" v-if="rebate?.reward_mode === 'test_card_hours' && estRebate > 0"><text class="sk">{{ t('rebateCenter') }}</text><text class="sv">{{ t('closedTestRewardBadge') }}</text></view>
        <view class="row"><text class="sk">{{ t('walletBalance') }}</text><text class="sv">{{ wallet == null ? '-' : fmtCH(wallet) }}</text></view>
      </view>
      <view v-if="canBuy" class="risk">{{ t(purchaseType === 'holding' ? 'holdingRisk' : 'usageRisk') }}</view>
    </scroll-view>
    <BottomActionBar v-if="product">
      <view class="buy-btn" :class="{ disabled: submitting || !canBuy }" @tap="openConfirm">{{ t(submitting ? '处理中...' : (!canBuy ? unavailableActionLabel : (purchaseType === 'holding' ? 'buyHolding' : 'buyUsage'))) }}</view>
    </BottomActionBar>
    <ConfirmSheet :visible="showConfirm" :title="t(purchaseType === 'holding' ? 'confirmHoldingPurchase' : 'confirmUsagePurchase')" :desc="product ? `${localizeProductName(product.name, i18n.lang)} × ${quantity} · ${cycleLabel(cycle)} · ${fmtCH(amount)}` : ''" :confirmText="t('k_936de2c4')" @cancel="showConfirm = false" @confirm="onBuy">
      <view class="confirm-fee">
        <text>{{ t('k_99b6bb88') }}</text>
        <text class="cf-val up">{{ fmtCH(amount) }}</text>
      </view>
      <view v-if="estRebate > 0" class="confirm-fee">
        <text>{{ t('k_64913945') }}</text>
        <text class="cf-val">+{{ fmtCardHours(estRebate) }} {{ t('cardHour') }}</text>
      </view>
    </ConfirmSheet>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { getProduct } from '@/api/gpu'
import { getMarketCandles, type MarketCandles } from '@/api/market'
import { createOrder } from '@/api/order'
import { getWallet } from '@/api/wallet'
import { getRebateSummary, type RebateSummary } from '@/api/user'
import { formatLocalDateTime, formatNumber, fmtCardHours, fmtCH, toCardHours } from '@/utils/format'
import AppNavBar from '@/components/AppNavBar.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import CandlestickChart from '@/components/CandlestickChart.vue'
import BottomActionBar from '@/components/BottomActionBar.vue'
import ConfirmSheet from '@/components/ConfirmSheet.vue'
import { navigateTo as nav } from '@/utils/nav'
import { useI18nStore } from '@/store/i18n'
import { localizeRegionName } from '@/utils/region-name'
import { localizePersonName, localizeProductName } from '@/utils/localize-content'
import { fallbackProductImage, resolveProductImage } from '@/utils/product-image'
import { isDirectCommerceEnabled } from '@/utils/ios-distribution'
import {
  historyProvenanceLabel,
  marketHistoryDisplayState,
  marketObservedDayCount,
} from '@/utils/market-history'

const i18n = useI18nStore()
const { t, tr } = i18n
const product = ref<Awaited<ReturnType<typeof getProduct>> | null>(null)
const candles = ref<MarketCandles | null>(null)
const cycle = ref(30)
const quantity = ref(1)
const purchaseType = ref<'usage' | 'holding'>('usage')
const wallet = ref<number | null>(null)
const rebate = ref<RebateSummary | null>(null)
const showConfirm = ref(false)
const submitting = ref(false)
const loading = ref(false)
const loadError = ref(false)
const partialLoadError = ref(false)
const productImageFailed = ref(false)
const pid = ref(0)
const pendingRequestId = ref('')
const pendingRequestSignature = ref('')
const directCommerceEnabled = isDirectCommerceEnabled()
let candleTimer: ReturnType<typeof setInterval> | null = null
const DEFAULT_PURCHASE_CYCLES = [1, 7, 30, 90, 180, 365]
const supplierName = computed(() => localizePersonName(product.value?.supplier_name || '', i18n.lang))
const productImageUrl = computed(() => productImageFailed.value
  ? fallbackProductImage(product.value?.gpu_model)
  : resolveProductImage(product.value?.image_url, product.value?.gpu_model))
const purchaseCycles = computed(() => {
  const cycles = product.value?.cycle || []
  return [...new Set([...DEFAULT_PURCHASE_CYCLES, ...cycles])].filter((days) => days > 0).sort((a, b) => a - b)
})
const maxQuantity = computed(() => {
  const stock = Number(product.value?.stock || 0)
  return Math.max(0, Math.min(Math.floor(stock), 99))
})
const canBuy = computed(() => Boolean(directCommerceEnabled && product.value?.purchasable === true && maxQuantity.value > 0))
const isProviderOffer = computed(() => Boolean(product.value?.market_source && product.value.market_source !== 'wod'))
const purchaseUnavailableText = computed(() => {
  if (!directCommerceEnabled) return t('iosCompanionCommerceNotice')
  if (maxQuantity.value <= 0) return t('noStockAvailable')
  if (product.value?.is_market_current === false) return t('marketOfferUnavailable')
  return t('wodListingUnavailable')
})
const unavailableActionLabel = computed(() => !directCommerceEnabled
  ? 'viewOnly'
  : product.value?.market_source && product.value.market_source !== 'wod'
    ? 'marketReferenceOnlyShort'
    : 'marketOfferUnavailableShort')
const sourceName = computed(() => {
  const source = product.value?.market_source
  if (source === 'vast') return 'Vast.ai'
  if (source === 'autodl') return 'AutoDL'
  if (!source || source === 'wod' || source === 'kai') return 'KAI'
  return localizePersonName(source, i18n.lang)
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
  const date = parseApiDate(product.value.price_updated_at)
  const formatted = formatLocalDateTime(date, i18n.lang) || t('notUpdated')
  return product.value.is_market_current ? formatted : `${formatted} · ${t(product.value.market_source_status === 'unavailable' ? 'sourceUnavailable' : 'staleData')}`
})

onLoad((opts) => {
  pid.value = Number(opts?.id || 0)
  loadProduct()
})
onShow(() => {
  startCandleTimer()
  void refreshProductState()
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
  wallet.value = null
  rebate.value = null

  const [productResult] = await Promise.allSettled([getProduct(pid.value)])

  if (productResult.status === 'rejected') {
    loadError.value = true
    loading.value = false
    return
  }

  product.value = productResult.value
  const source = product.value.market_source || 'wod'
  const [candleResult, walletResult, rebateResult] = await Promise.allSettled([
    getMarketCandles(
      product.value.gpu_model,
      product.value.memory || '',
      '7d',
      [source],
      false,
      source === 'wod' ? 'wod_listing' : 'ondemand',
    ),
    getWallet(),
    getRebateSummary(),
  ])
  if (candleResult.status === 'fulfilled') candles.value = candleResult.value
  if (walletResult.status === 'fulfilled') wallet.value = walletResult.value.balance
  if (rebateResult.status === 'fulfilled') rebate.value = rebateResult.value
  partialLoadError.value = candleResult.status === 'rejected'
    || walletResult.status === 'rejected'
    || rebateResult.status === 'rejected'
  if (!purchaseCycles.value.includes(cycle.value)) {
    cycle.value = purchaseCycles.value[0] || 30
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
    quantity.value = Math.min(Math.max(quantity.value, 1), Math.max(maxQuantity.value, 1))
  } catch {
    // Keep the last successfully loaded detail during a transient refresh.
  }
}

async function refreshCandles(silent = true) {
  const current = product.value
  if (!current) return
  const source = current.market_source || 'wod'
  try {
    candles.value = await getMarketCandles(
      current.gpu_model,
      current.memory || '',
      '7d',
      [source],
      silent,
      source === 'wod' ? 'wod_listing' : 'ondemand',
    )
  } catch {
    // Keep the last verified candles during a transient refresh failure.
  }
}

function startCandleTimer() {
  stopCandleTimer()
  candleTimer = setInterval(() => refreshCandles(true), 10000)
}

function stopCandleTimer() {
  if (candleTimer) clearInterval(candleTimer)
  candleTimer = null
}

const amount = computed(() => (product.value ? product.value.price * cycle.value * 24 * quantity.value : 0))

function changeQuantity(delta: number) {
  if (!canBuy.value) return
  quantity.value = Math.max(1, Math.min(quantity.value + delta, maxQuantity.value))
}
function quantityUnits(count: number) {
  if (i18n.lang === 'en') return `${count} ${count === 1 ? 'GPU' : 'GPUs'}`
  return t('quantityUnits', { count })
}

function cycleLabel(days: number) {
  const labels: Record<number, string> = {
    1: 'oneDayCycle',
    7: 'sevenDaysCycle',
    30: 'thirtyDaysCycle',
    90: 'threeMonthsCycle',
    180: 'sixMonthsCycle',
    365: 'oneYearCycle',
  }
  return labels[days] ? t(labels[days]) : t('{days} 天', { days })
}
// 预计返佣 = 购买卡时 × 当前返佣比例
const estRebateRate = computed(() => {
  const total = Number(rebate.value?.month_spent || 0) + toCardHours(amount.value || 0)
  if (total <= 10000) return 3
  if (total <= 50000) return 5
  if (total <= 100000) return 7
  return 10
})
const estRebate = computed(() => {
  if (purchaseType.value !== 'usage' || !rebate.value?.rewards_enabled || !amount.value) return 0
  return toCardHours(amount.value) * estRebateRate.value / 100
})

async function onBuy() {
  showConfirm.value = false
  if (submitting.value || !directCommerceEnabled || !canBuy.value) return
  submitting.value = true
  try {
    const created = await createOrder(pid.value, cycle.value, purchaseType.value, quantity.value, ensureRequestId())
    pendingRequestId.value = ''
    pendingRequestSignature.value = ''
    uni.showToast({ title: t('购买成功'), icon: 'success' })
    setTimeout(() => nav(`/pages/order/detail?id=${created.id}`), 800)
  } catch {
    /* request toast */
  }
  submitting.value = false
}

function openConfirm() {
  if (!directCommerceEnabled) {
    uni.showToast({ title: t('iosCompanionCommerceNotice'), icon: 'none' })
    return
  }
  if (!canBuy.value) {
    uni.showToast({ title: purchaseUnavailableText.value, icon: 'none' })
    return
  }
  ensureRequestId()
  showConfirm.value = true
}

function ensureRequestId() {
  const signature = `${pid.value}:${cycle.value}:${quantity.value}:${purchaseType.value}`
  if (!pendingRequestId.value || pendingRequestSignature.value !== signature) {
    pendingRequestSignature.value = signature
    pendingRequestId.value = `wod-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
  }
  return pendingRequestId.value
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
.ph { display: flex; justify-content: space-between; align-items: center; padding: 24rpx 0 32rpx; }
.pn { color: var(--text); font-size: 44rpx; font-weight: 700; }
.pmem { color: var(--primary); font-size: 24rpx; background: var(--primary-soft); padding: 6rpx 18rpx; border-radius: var(--radius); }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--border); }
.trend-card { padding: 12rpx 12rpx 4rpx; overflow: hidden; }
.history-empty { padding: 72rpx 28rpx; color: var(--text-sub); font-size: 24rpx; text-align: center; }
.price-box { padding: 40rpx 32rpx; margin-bottom: 24rpx; background: var(--card); border: none; box-shadow: 0 4rpx 24rpx var(--card-border); }
.pp { color: var(--text); font-size: 56rpx; font-weight: 800; font-variant-numeric: tabular-nums; }
.pu { color: var(--text-sub); font-size: 26rpx; }
.daily { display: block; color: var(--up); font-size: 26rpx; margin-top: 12rpx; }
.daily.muted { color: var(--text-sub); }
.specs { padding: 8rpx 32rpx; margin-bottom: 24rpx; }
.row { display: flex; justify-content: space-between; align-items: center; padding: 28rpx 0; border-bottom: 1rpx solid var(--divider); }
.row:last-child { border-bottom: none; }
.sk { color: var(--text-sub); font-size: 28rpx; }
.sv { color: var(--text); font-size: 28rpx; font-variant-numeric: tabular-nums; }
.sv.stale { color: var(--down); }
.up { color: var(--up); }
.offer-warning { color: var(--down); background: rgba(217, 72, 72, 0.08); border: 1rpx solid rgba(217, 72, 72, 0.22); border-radius: var(--radius); padding: 20rpx 24rpx; margin-bottom: 24rpx; font-size: 24rpx; line-height: 1.5; }
.provider-notice { color: var(--text-sub); background: var(--primary-soft); border: 1rpx solid var(--card-border); border-radius: var(--radius); padding: 20rpx 24rpx; margin-bottom: 24rpx; font-size: 24rpx; line-height: 1.5; }
.cycles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16rpx; margin-bottom: 24rpx; }
.cycle { min-width: 0; text-align: center; padding: 24rpx 8rpx; border: 1rpx solid var(--border); border-radius: var(--radius); color: var(--text-sub); font-size: 28rpx; background: var(--card); }
.cycle.active { border-color: var(--primary); color: var(--primary); background: var(--primary-soft); }
.quantity-row { display: flex; align-items: center; justify-content: space-between; gap: 24rpx; padding: 22rpx 24rpx; margin-bottom: 24rpx; background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }
.quantity-label { display: block; color: var(--text); font-size: 28rpx; font-weight: 650; font-variant-numeric: tabular-nums; }
.quantity-stock { display: block; color: var(--text-sub); font-size: 21rpx; margin-top: 6rpx; }
.quantity-stepper { display: grid; grid-template-columns: 64rpx 72rpx 64rpx; align-items: center; border: 1rpx solid var(--border); border-radius: 12rpx; overflow: hidden; }
.quantity-button { height: 64rpx; display: flex; align-items: center; justify-content: center; color: var(--primary); background: var(--primary-soft); font-size: 34rpx; font-weight: 600; }
.quantity-button:active { transform: scale(0.96); }
.quantity-button.disabled { color: var(--text-dim); background: var(--bg-2); }
.quantity-value { color: var(--text); text-align: center; font-size: 28rpx; font-weight: 700; font-variant-numeric: tabular-nums; }
.mode-row { display: flex; gap: 16rpx; margin-bottom: 24rpx; }
.mode-card { flex: 1; padding: 24rpx; border: 2rpx solid var(--border); border-radius: var(--radius); display: flex; flex-direction: column; gap: 8rpx; background: var(--card); }
.mode-card.active { border-color: var(--primary); background: var(--primary-soft); }
.mode-title { color: var(--text); font-size: 28rpx; font-weight: 700; }
.mode-card.active .mode-title { color: var(--primary); }
.mode-desc { color: var(--text-sub); font-size: 22rpx; line-height: 1.4; }
.fee { padding: 8rpx 32rpx; margin-bottom: 24rpx; }
.risk { color: var(--text-dim); font-size: 24rpx; padding: 16rpx 8rpx; line-height: 1.6; }
.buy-btn { background: var(--primary); color: #fff; text-align: center; padding: 28rpx 0; border-radius: var(--radius); font-size: 32rpx; font-weight: 600; }
.buy-btn.disabled { opacity: 0.5; }
.confirm-fee { display: flex; justify-content: space-between; align-items: center; padding: 16rpx 0; }
.cf-val { font-size: 40rpx; font-weight: 700; font-variant-numeric: tabular-nums; }

.store-link { display: flex; align-items: center; justify-content: space-between; padding: 28rpx 32rpx; margin-bottom: 24rpx; }
.sl-info { display: flex; align-items: center; gap: 20rpx; }
.sl-avatar { width: 64rpx; height: 64rpx; border-radius: 32rpx; background: linear-gradient(135deg, var(--primary), var(--primary)); color: #fff; font-size: 28rpx; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.sl-name { color: var(--text); font-size: 30rpx; font-weight: 600; }
.sl-go { color: var(--primary); font-size: 26rpx; }
</style>
