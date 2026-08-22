<template>
  <view class="page">
    <view class="shell" :style="{ paddingTop: 'calc(20rpx + var(--safe-top))' }">
      <view class="topbar">
        <view>
          <text class="hi">{{ t('hello') }}</text>
          <text class="uname">{{ displayUsername }}</text>
        </view>
        <view class="top-actions">
          <view class="top-action-hit" @tap="go('/pages/notifications/index')">
            <AppIcon name="bell" :size="36" />
            <text v-if="notificationStore.unread > 0" class="notification-badge">{{ notificationBadge }}</text>
          </view>
          <LanguageToggle />
          <ThemeToggle />
        </view>
      </view>

      <view class="hero">
        <text class="hero-label">{{ t('totalAssets') }}</text>
        <text class="hero-val">{{ fmtCHn(totalAsset) }}</text>
        <view class="hero-row">
          <view class="hero-sub">
            <text class="sub-label">{{ t('todayRevenue') }}</text>
            <text class="sub-val up">+{{ fmtCHn(rev?.today) }}</text>
          </view>
          <view class="hero-sub">
            <text class="sub-label">{{ t('totalRevenue') }}</text>
            <text class="sub-val">{{ fmtCH(rev?.total) }}</text>
          </view>
        </view>
      </view>

      <view class="divider"></view>

      <view v-if="homeLoadError" class="home-load-warning">
        <text>{{ t('partialAssetDataUnavailable') }}</text>
        <text class="home-load-retry" role="button" @tap="load">{{ t('retry') }}</text>
      </view>

      <scroll-view scroll-x class="price-bar" :show-scrollbar="false">
        <view class="pb-item" v-for="p in hot" :key="p.id" @tap="go('/pages/product/detail?id=' + p.id)">
          <text class="pb-name">{{ p.gpu_model }}</text>
          <text class="pb-price">{{ fmtCH(p.price) }}/h</text>
          <text class="pb-change" :class="changeTone(modelChange(p))">{{ modelChangeText(p) }}</text>
        </view>
      </scroll-view>

      <view class="divider"></view>

      <view class="quick">
        <view class="q-item" @tap="go('/pages/wallet/index')">
          <view class="q-icon"><AppIcon name="wallet" :size="36" /></view>
          <text class="q-text">{{ t('recharge') }}</text>
        </view>
        <view class="q-item" @tap="go('/pages/wallet/index')">
          <view class="q-icon"><AppIcon name="arrow-right" :size="36" /></view>
          <text class="q-text">{{ t('withdraw') }}</text>
        </view>
        <view class="q-item" @tap="goTab('/pages/market/index')">
          <view class="q-icon"><AppIcon name="gpu" :size="36" /></view>
          <text class="q-text">{{ t('buyCompute') }}</text>
        </view>
        <view class="q-item" @tap="go('/pages/orders/index')">
          <view class="q-icon"><AppIcon name="order" :size="36" /></view>
          <text class="q-text">{{ t('orders') }}</text>
        </view>
      </view>

      <SectionHeader :title="t('runningCompute')">
        <template #extra><text class="more" @tap="goTab('/pages/assets/index')">{{ t('all') }} ›</text></template>
      </SectionHeader>
      <view v-if="!assets.length" class="empty">{{ t("noRunning") }}</view>
      <scroll-view scroll-x class="asset-scroll" :show-scrollbar="false">
        <view v-for="a in assets" :key="a.id" class="card arow-s" @tap="go('/pages/asset/detail?id=' + a.id)">
          <view class="al">
          <text class="an">{{ localizeProductName(a.product_name, i18n.lang) }}</text>
            <text class="ag">{{ a.gpu_model }} · {{ t('剩余 {days} 天', { days: a.remaining_days ?? 0 }) }}</text>
          </view>
          <view class="ar">
            <text class="av up">+{{ fmtCHn(a.today_revenue) }}</text>
            <text class="al2">{{ t('today') }}</text>
          </view>
        </view>
      </scroll-view>

      <SectionHeader :title="t('hotComputeTrends')">
        <template #extra><text class="more" @tap="go('/pages/quote/index')">{{ t('viewMarket') }} ›</text></template>
      </SectionHeader>
      <view v-if="hotMarketLoading" class="hot-market-panel hot-market-skeleton">
        <view class="hot-sk-tabs"><view v-for="item in 3" :key="item"></view></view>
        <view class="hot-sk-head"></view>
        <view class="hot-sk-chart"></view>
      </view>
      <view v-else-if="hotMarketError && !hotTrends.length" class="hot-market-panel hot-market-empty">
        <text>{{ t('dataUnavailable') }}</text>
        <text class="hot-market-retry" role="button" @tap="loadHotMarket(false, true)">{{ t('retry') }}</text>
      </view>
      <view v-else-if="!hotTrends.length" class="hot-market-panel hot-market-empty">{{ t('noHotMarketData') }}</view>
      <view v-else class="hot-market-panel">
        <scroll-view scroll-x class="hot-model-tabs-scroll" :show-scrollbar="false">
          <view class="hot-model-tabs">
            <view v-for="(trend, index) in hotTrends" :key="`${trend.item.gpu_model}-${trend.item.gpu_variant}`" class="hot-model-tab" :class="{ active: hotTrendIndex === index }" @tap="hotTrendIndex = index">
              <text>{{ trend.item.gpu_model }}</text>
              <text>{{ trend.item.gpu_variant || t('standardVariant') }}</text>
            </view>
          </view>
        </scroll-view>
        <template v-if="activeHotTrend">
          <view class="hot-market-head" @tap="goTrend(activeHotTrend)">
            <view>
              <text class="hot-model">{{ activeHotTrend.item.gpu_model }}</text>
              <text class="hot-variant">{{ activeHotTrend.item.gpu_variant || t('standardVariant') }}</text>
            </view>
            <view class="hot-market-value">
              <text class="hot-price">{{ activeHotTrend.item.median_price_cny == null ? '--' : fmtCHr(activeHotTrend.item.median_price_cny) }}</text>
              <text class="hot-change" :class="changeTone(trendSevenDayChange(activeHotTrend))">{{ trendChangeText(activeHotTrend) }}</text>
              <text v-if="trendHasFullHistory(activeHotTrend)" class="hot-range">{{ priceRangeText(activeHotTrend.item) }}</text>
            </view>
          </view>
          <view class="hot-full-chart" @tap="retryActiveTrend">
            <CandlestickChart
              :candles="activeHotTrend.candles?.candles || []"
              :source-note="historySourceText(activeHotTrend)"
              :history-state="marketHistoryDisplayState(activeHotTrend.candles)"
              :observed-days="marketObservedDayCount(activeHotTrend.candles)"
              :reference-price-cny="activeHotTrend.candles?.latest_live_price_cny ?? activeHotTrend.item.median_price_cny"
              :reference-sample-count="activeHotTrend.item.sample_count"
              :reference-observed-at="activeHotTrend.candles?.latest_live_observed_at || ''"
              :loading="activeHotTrend.state === 'loading'"
              :error="activeHotTrend.state === 'error'"
            />
          </view>
        </template>
      </view>

      <SectionHeader :title="t('revenueTrend')">
        <template #extra><text class="more" @tap="go('/pages/revenue/index')">{{ t('detail') }} ›</text></template>
      </SectionHeader>
      <view class="card chart-card">
        <Chart :points="chart" value-key="amount" :height="140" />
      </view>

      <SectionHeader :title="t('featuredCompute')">
        <template #extra><text class="more" @tap="goTab('/pages/market/index')">{{ t('more') }} ›</text></template>
      </SectionHeader>
      <view v-if="featuredLoading && !hot.length" class="featured-list-skeleton" aria-busy="true">
        <view v-for="item in 4" :key="item" class="card featured-skeleton-row">
          <view class="featured-sk-image"></view>
          <view class="featured-sk-copy"><view></view><view></view></view>
          <view class="featured-sk-price"></view>
        </view>
      </view>
      <view v-else-if="featuredError && !hot.length" class="featured-state">
        <text>{{ t('dataUnavailable') }}</text>
        <text class="hot-market-retry" role="button" @tap="retryFeaturedProducts">{{ t('retry') }}</text>
      </view>
      <view v-else-if="!hot.length" class="featured-state">{{ t('noHotMarketData') }}</view>
      <template v-else>
        <view v-for="p in hot" :key="p.id" class="card prow" @tap="go('/pages/product/detail?id=' + p.id)">
          <image class="pimg" :src="productImage(p)" mode="aspectFill" lazy-load :fade-show="false" @error="markProductImageFailed(p.id)" />
          <view class="pl">
            <text class="pn">{{ localizeProductName(p.name, i18n.lang) }}</text>
            <text class="pm">{{ p.memory }} · {{ t('revenueDataUnavailable') }}</text>
          </view>
          <view class="pr">
            <text class="pp">{{ fmtCH(p.price) }}</text>
            <text class="pu">/h</text>
            <text class="p-buy">{{ t(p.purchasable ? 'buyUsage' : 'viewDetail') }}</text>
          </view>
        </view>
      </template>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onHide, onShow, onUnload } from '@dcloudio/uni-app'
import { useUserStore } from '@/store/user'
import { useAssetStore } from '@/store/asset'
import { useNotificationStore } from '@/store/notification'
import { getWallet } from '@/api/wallet'
import { getRevenueSummary, getRevenueChart } from '@/api/revenue'
import { getProducts } from '@/api/gpu'
import { getMarketCandles, getMarketRanking, type MarketCandles, type MarketRankingItem } from '@/api/market'
import { fmtCH, fmtCHr, fmtCHn } from '@/utils/format'
import { navigateTo as go } from '@/utils/nav'
import type { Product } from '@/api/gpu'
import type { RevenueSummary, RevenuePoint } from '@/api/revenue'
import AppIcon from '@/components/AppIcon.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import Chart from '@/components/Chart.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import LanguageToggle from '@/components/LanguageToggle.vue'
import CandlestickChart from '@/components/CandlestickChart.vue'
import { useI18nStore } from '@/store/i18n'
import { localizePersonName, localizeProductName } from '@/utils/localize-content'
import { formatSignedMarketPercentNumber } from '@/utils/market-chart'
import { fallbackProductImage, resolveProductImage } from '@/utils/product-image'
import {
  hasCompleteSevenDayMetric,
  selectFeaturedProducts,
  trustedSevenDayChange,
  trustedSevenDayPriceRange,
} from '@/utils/market-list'
import {
  hasCompleteSevenDayCandles,
  historyProvenanceLabel,
  marketHistoryDisplayState,
  marketObservedDayCount,
} from '@/utils/market-history'
import {
  buildHomeTrendRequests,
  HOME_CANDLE_REFRESH_MS,
  HOME_RANKING_REFRESH_MS,
  HOME_TREND_LIMIT,
  isHomeMarketStatusDisplayable,
} from '@/utils/home-market-policy'

const userStore = useUserStore()
const assetStore = useAssetStore()
const notificationStore = useNotificationStore()
const i18n = useI18nStore()
const { t } = i18n
const user = computed(() => userStore.userInfo)
const displayUsername = computed(() => localizePersonName(user.value?.username || '体验用户', i18n.lang))
const rev = ref<RevenueSummary | null>(null)
const chart = ref<RevenuePoint[]>([])
const hot = ref<Product[]>([])
const productPool = ref<Product[]>([])
const failedProductImages = ref<Record<number, boolean>>({})
const featuredLoading = ref(true)
const featuredError = ref(false)
const walletBalance = ref(0)
const homeLoadError = ref(false)
type ModelRange = Pick<MarketRankingItem, 'change_7d_pct' | 'range_low_cny' | 'range_high_cny' | 'history_day_count' | 'history_span_hours' | 'history_provenance' | 'market_status'>
type HotTrendState = 'loading' | 'ready' | 'empty' | 'error'
type HotTrend = { item: MarketRankingItem; candles: MarketCandles | null; state: HotTrendState }
const volatilityMap = ref<Record<string, ModelRange>>({})
const hotTrends = ref<HotTrend[]>([])
const hotMarketLoading = ref(true)
const hotMarketError = ref(false)
const hotTrendIndex = ref(0)
let marketTimer: ReturnType<typeof setInterval> | null = null
let hotMarketInFlight = false
let rankingLoadedAt = 0
let cachedPopularModels: MarketRankingItem[] = []
let candlesLoadedAt = 0
let candleCandidateSignature = ''

const totalAsset = computed(() => (assetStore.summary?.total_value ?? 0) + walletBalance.value)
const assets = computed(() => assetStore.summary?.items ?? [])
const activeHotTrend = computed(() => hotTrends.value[hotTrendIndex.value] || hotTrends.value[0] || null)
const notificationBadge = computed(() => notificationStore.unread > 99 ? '99+' : String(notificationStore.unread))

async function load() {
  const [walletResult, revenueResult, chartResult, productsResult, assetsResult] = await Promise.allSettled([
    getWallet(), getRevenueSummary(), getRevenueChart(7), loadFeaturedProducts(), assetStore.refresh(),
  ])
  if (walletResult.status === 'fulfilled') walletBalance.value = walletResult.value.balance
  if (revenueResult.status === 'fulfilled') rev.value = revenueResult.value
  if (chartResult.status === 'fulfilled') chart.value = chartResult.value
  homeLoadError.value = [walletResult, revenueResult, chartResult, productsResult, assetsResult]
    .some((result) => result.status === 'rejected')
}

async function loadFeaturedProducts(silent = true) {
  if (!productPool.value.length) featuredLoading.value = true
  try {
    const response = await getProducts({ page_size: 24 })
    productPool.value = response.items
    updateHotProducts()
    featuredError.value = false
  } catch (error) {
    featuredError.value = true
    if (!silent && !productPool.value.length) {
      uni.showToast({ title: t('dataUnavailable'), icon: 'none' })
    }
    throw error
  } finally {
    featuredLoading.value = false
  }
}

function gpuKey(value: string, variant = '') {
  return `${String(value || '').replace(/\s+/g, '').toUpperCase()}|${String(variant || '').replace(/\s+/g, '').toUpperCase()}`
}
function updateHotProducts() {
  hot.value = selectFeaturedProducts(productPool.value, volatilityMap.value, 4)
}

async function loadHotMarket(silent = true, forceCandles = false) {
  if (hotMarketInFlight) return
  if (typeof document !== 'undefined' && document.hidden && silent) return
  hotMarketInFlight = true
  try {
    // Seven-day ranking is substantially heavier than the current candle
    // query and does not change every ten seconds. Reuse it briefly while the
    // real candles continue to refresh on the requested ten-second cadence.
    if (!rankingLoadedAt || Date.now() - rankingLoadedAt >= HOME_RANKING_REFRESH_MS) {
      const ranking = await getMarketRanking(silent)
      volatilityMap.value = {}
      for (const item of ranking.items) {
        const key = gpuKey(item.gpu_model, item.gpu_variant)
        const existing = volatilityMap.value[key]
        if (!existing || metricPriority(item) > metricPriority(existing)) {
          volatilityMap.value[key] = item
        }
      }
      updateHotProducts()
      const liveCandidates = ranking.items
        .filter((item) => isHomeMarketStatusDisplayable(item.market_status) && item.median_price_cny != null && item.sample_count > 0)
      const completeCandidates = liveCandidates.filter(hasCompleteSevenDayMetric)
      cachedPopularModels = (completeCandidates.length ? completeCandidates.concat(liveCandidates) : liveCandidates)
        .sort(compareHomeMarketCandidate)
        .filter((item, index, items) => items.findIndex((candidate) => gpuKey(candidate.gpu_model, candidate.gpu_variant) === gpuKey(item.gpu_model, item.gpu_variant)) === index)
        .slice(0, HOME_TREND_LIMIT)
      rankingLoadedAt = Date.now()
    }
    const plan = buildHomeTrendRequests(cachedPopularModels)
    const signature = plan.map((request) => `${request.key}|${request.sources.join(',')}|${request.billingMode}`).join(';')
    const existingByKey = new Map(hotTrends.value.map((trend) => [gpuKey(trend.item.gpu_model, trend.item.gpu_variant), trend]))
    // Keep the current quote fields fresh every ten seconds without reloading
    // a seven-day archive whose display bucket is six hours.
    hotTrends.value = plan.map((request) => {
      const existing = existingByKey.get(request.key)
      return existing
        ? { ...existing, item: request.item }
        : { item: request.item, candles: null, state: 'loading' as const }
    })
    const needsCandles = forceCandles
      || signature !== candleCandidateSignature
      || Date.now() - candlesLoadedAt >= HOME_CANDLE_REFRESH_MS
      || !hotTrends.value.length
    if (needsCandles && plan.length) {
      // The ranking has already proved history coverage. Fetch at most three
      // exact identities, once, instead of walking a fallback list every tick.
      const settled = await Promise.allSettled(plan.map(async (request) => ({
        item: request.item,
        candles: await getMarketCandles(
          request.item.gpu_model,
          request.item.gpu_variant,
          '7d',
          request.sources,
          silent,
          request.billingMode,
        ),
      })))
      hotTrends.value = settled.map((result, index): HotTrend => {
        const previous = existingByKey.get(plan[index].key)
        if (result.status === 'rejected') {
          return previous?.candles
            ? { item: plan[index].item, candles: previous.candles, state: 'ready' }
            : { item: plan[index].item, candles: null, state: 'error' }
        }
        const candles = result.value.candles
        const renderable = candles.candles.length > 0
          || candles.latest_live_price_cny != null
          || result.value.item.median_price_cny != null
        return {
          item: result.value.item,
          candles,
          state: renderable ? 'ready' : 'empty',
        }
      })
      candlesLoadedAt = Date.now()
      candleCandidateSignature = signature
    }
    hotMarketError.value = false
    if (hotTrendIndex.value >= hotTrends.value.length) hotTrendIndex.value = 0
  } catch {
    hotMarketError.value = true
  } finally {
    hotMarketLoading.value = false
    hotMarketInFlight = false
  }
}

function startMarketTimer() {
  stopMarketTimer()
  marketTimer = setInterval(() => loadHotMarket(true), 10000)
}

function sourceLabel(source: string) {
  if (source === 'vast') return 'Vast.ai'
  if (source === 'autodl') return 'AutoDL'
  return source === 'wod' ? '北斗 kai' : source
}

function stopMarketTimer() {
  if (marketTimer) { clearInterval(marketTimer); marketTimer = null }
}

function retryActiveTrend() {
  if (activeHotTrend.value?.state === 'error') loadHotMarket(false, true)
}

function retryFeaturedProducts() {
  loadFeaturedProducts(false).catch(() => {})
}

onShow(() => {
  i18n.updateTabBar()
  if (!userStore.isLogin) { uni.reLaunch({ url: '/pages/login/index' }); return }
  Promise.all([load(), loadHotMarket(false)]).catch(() => {})
  notificationStore.refresh(true).catch(() => {})
  startMarketTimer()
})
onHide(stopMarketTimer)
onUnload(stopMarketTimer)

function reload() { load() }
function goTab(url: string) { uni.switchTab({ url }) }
function modelRange(p: Pick<Product, 'gpu_model' | 'memory'>): ModelRange | undefined { return volatilityMap.value[gpuKey(p.gpu_model, p.memory)] }
function metricPriority(metric?: ModelRange): number {
  if (!hasCompleteSevenDayMetric(metric)) return -1
  return Math.abs(trustedSevenDayChange(metric) || 0)
}
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
function compareModelRange(a: Pick<Product, 'gpu_model' | 'memory'>, b: Pick<Product, 'gpu_model' | 'memory'>): number {
  const av = modelChange(a)
  const bv = modelChange(b)
  if (av == null && bv == null) return 0
  if (av == null) return 1
  if (bv == null) return -1
  return Math.abs(bv) - Math.abs(av)
}
function sevenDayChange(item: MarketRankingItem): number | null {
  return hasCompleteSevenDayMetric(item) ? trustedSevenDayChange(item) : null
}
function changeText(item: MarketRankingItem): string {
  const value = sevenDayChange(item)
  return value == null
    ? (Number(item.history_day_count || 0) > 1 ? t('chartObservedDays', { days: item.history_day_count }) : t('currentQuoteBaseline'))
    : t('sevenDayChangeValue', { value: formatSignedMarketPercentNumber(value) })
}
function priceRangeText(item: MarketRankingItem): string {
  const range = hasCompleteSevenDayMetric(item) ? trustedSevenDayPriceRange(item) : null
  return range
    ? t('sevenDayPriceRangeValue', { low: fmtCHn(range.low), high: fmtCHn(range.high) })
    : (Number(item.history_day_count || 0) > 1 ? t('chartObservedDays', { days: item.history_day_count }) : t('currentQuoteBaseline'))
}
function trendHasFullHistory(trend: HotTrend): boolean {
  return hasCompleteSevenDayCandles(trend.candles)
}
function trendSevenDayChange(trend: HotTrend): number | null {
  return trendHasFullHistory(trend) ? sevenDayChange(trend.item) : null
}
function trendChangeText(trend: HotTrend): string {
  const value = trendSevenDayChange(trend)
  if (value != null) return t('sevenDayChangeValue', { value: formatSignedMarketPercentNumber(value) })
  return marketHistoryDisplayState(trend.candles) === 'partial'
    ? t('chartObservedDays', { days: marketObservedDayCount(trend.candles) })
    : t('currentQuoteBaseline')
}
function changeTone(value: number | null): string {
  return value == null || value === 0 ? 'neutral' : value > 0 ? 'rise' : 'fall'
}
function compareHomeMarketCandidate(a: MarketRankingItem, b: MarketRankingItem): number {
  const aModel = gpuKey(a.gpu_model).split('|')[0]
  const bModel = gpuKey(b.gpu_model).split('|')[0]
  const a4090 = aModel === 'RTX4090' ? 1 : 0
  const b4090 = bModel === 'RTX4090' ? 1 : 0
  if (a4090 !== b4090) return b4090 - a4090
  const aOfficial = a.history_provenance?.kind === 'official' ? 1 : 0
  const bOfficial = b.history_provenance?.kind === 'official' ? 1 : 0
  if (aOfficial !== bOfficial) return bOfficial - aOfficial
  return b.available_gpu_count - a.available_gpu_count || b.sample_count - a.sample_count
}
function historySourceText(trend: HotTrend): string {
  return historyProvenanceLabel(trend.candles?.provenance || trend.item.history_provenance, t)
    || trend.candles?.requested_sources.map(sourceLabel).join(' · ')
    || trend.item.sources.map(sourceLabel).join(' · ')
}
function goTrend(trend: { item: MarketRankingItem }) {
  const model = encodeURIComponent(trend.item.gpu_model)
  const variant = encodeURIComponent(trend.item.gpu_variant || '')
  go(`/pages/quote/index?model=${model}&variant=${variant}`)
}
function productImage(product: Pick<Product, 'id' | 'image_url' | 'gpu_model'>) {
  return failedProductImages.value[product.id]
    ? fallbackProductImage(product.gpu_model)
    : resolveProductImage(product.image_url, product.gpu_model)
}
function markProductImageFailed(id: number) {
  if (!failedProductImages.value[id]) failedProductImages.value = { ...failedProductImages.value, [id]: true }
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 20px calc(132rpx + var(--safe-bottom)); }

.topbar { position: relative; z-index: 2; display: flex; justify-content: space-between; align-items: center; min-height: 88rpx; padding: 8rpx 0 20rpx; }
.hi { color: var(--text-sub); font-size: 13px; }
.uname { color: var(--text); font-size: 15px; font-weight: 700; }
.top-actions { display: flex; gap: 8px; align-items: center; color: var(--text-sub); }
.top-action-hit { position: relative; width: 88rpx; height: 88rpx; display: flex; align-items: center; justify-content: center; }
.notification-badge { position: absolute; top: 5rpx; right: 2rpx; min-width: 28rpx; height: 28rpx; padding: 0 7rpx; display: flex; align-items: center; justify-content: center; box-sizing: border-box; border-radius: 14rpx; background: var(--down); color: #fff; font-size: 17rpx; font-weight: 700; line-height: 1; }

.hero { padding: 8px 0 16px; }
.hero-label { display: block; color: var(--text-sub); font-size: 12px; letter-spacing: 0.5px; }
.hero-val { display: block; color: var(--text); font-size: 38px; font-weight: 800; margin-top: 4px; font-variant-numeric: tabular-nums; letter-spacing: -1px; }
.hero-row { display: flex; gap: 24px; margin-top: 12px; }
.hero-sub { display: flex; flex-direction: column; }
.sub-label { color: var(--text-sub); font-size: 11px; }
.sub-val { color: var(--text); font-size: 14px; font-weight: 700; margin-top: 2px; font-variant-numeric: tabular-nums; }
.up { color: var(--up); }

.divider { height: 1px; background: var(--divider); margin: 0; }
.home-load-warning { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; padding: 18rpx 22rpx; margin: 18rpx 0 0; color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); font-size: 22rpx; line-height: 1.45; }
.home-load-retry { min-height: 64rpx; flex-shrink: 0; display: flex; align-items: center; color: var(--primary); font-weight: 700; }

.price-bar { white-space: nowrap; padding: 14px 0; }
.pb-item { display: inline-flex; flex-direction: column; align-items: center; padding: 16px 24px; margin-right: 10px; background: var(--card); border: 1px solid var(--card-border); border-radius: var(--radius); min-width: 160rpx; }
.pb-name { color: var(--text-sub); font-size: 11px; }
.pb-price { color: var(--primary); font-size: 14px; font-weight: 700; margin-top: 2px; font-variant-numeric: tabular-nums; }
.pb-change { font-size: 10px; font-weight: 600; margin-top: 2px; }
.pb-change.rise { color: #E5484D; }
.pb-change.fall { color: #168A5B; }
.pb-change.neutral { color: var(--text-dim); }

.quick { display: flex; gap: 8px; padding: 16px 0; }
.q-item { flex: 1; display: flex; flex-direction: column; align-items: center; padding: 14px 0; background: var(--card); border: 1px solid var(--card-border); border-radius: var(--radius); }
.q-icon { margin-bottom: 6px; color: var(--primary); width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; background: var(--primary-soft); }
.q-text { color: var(--text); font-size: 11px; }

.more { color: var(--text-sub); font-size: 12px; }
.empty { padding: 40rpx 0; text-align: center; color: var(--text-sub); font-size: 13px; }

.chart-card { padding: 16px; margin-bottom: 12px; }

.hot-market-panel { background: var(--card); border: 1px solid var(--card-border); border-radius: var(--radius); overflow: hidden; margin-bottom: 12px; }
.hot-model-tabs-scroll { width: 100%; white-space: nowrap; border-bottom: 1px solid var(--divider); }
.hot-model-tabs { display: inline-flex; min-width: 100%; padding: 10rpx; box-sizing: border-box; gap: 8rpx; }
.hot-model-tab { width: 172rpx; flex: 0 0 172rpx; min-width: 0; display: flex; align-items: baseline; justify-content: center; gap: 6rpx; padding: 15rpx 8rpx; box-sizing: border-box; border-radius: 10rpx; color: var(--text-sub); }
.hot-model-tab text:first-child { font-size: 22rpx; font-weight: 700; overflow: hidden; text-overflow: ellipsis; }
.hot-model-tab text:last-child { font-size: 17rpx; white-space: nowrap; }
.hot-model-tab.active { color: var(--primary); background: var(--primary-soft); }
.hot-market-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18rpx; padding: 22rpx 24rpx 8rpx; }
.hot-market-head:active { opacity: 0.72; }
.hot-market-value { min-width: 0; max-width: 62%; }
.hot-model { display: block; color: var(--text); font-size: 25rpx; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hot-variant { display: block; color: var(--text-sub); font-size: 18rpx; margin-top: 4rpx; white-space: nowrap; }
.hot-market-value { text-align: right; }
.hot-price { display: block; color: var(--primary); font-size: 23rpx; font-weight: 750; font-variant-numeric: tabular-nums; white-space: nowrap; }
.hot-change { display: block; color: var(--text-dim); font-size: 18rpx; line-height: 1.35; margin-top: 4rpx; white-space: normal; }
.hot-change.rise { color: #E5484D; }
.hot-change.fall { color: #168A5B; }
.hot-range { display: block; color: var(--text-sub); font-size: 17rpx; line-height: 1.35; margin-top: 3rpx; }
.hot-full-chart { padding: 0 8rpx; }
.hot-market-empty { padding: 38rpx 20rpx; color: var(--text-sub); text-align: center; font-size: 22rpx; display: flex; flex-direction: column; align-items: center; gap: 18rpx; }
.hot-market-retry { min-height: 64rpx; padding: 0 26rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: var(--radius); font-weight: 700; }
.hot-market-skeleton { padding: 10rpx 20rpx 24rpx; }
.hot-sk-tabs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12rpx; }
.hot-sk-tabs view { height: 48rpx; border-radius: 10rpx; background: var(--divider); }
.hot-sk-head { width: 44%; height: 22rpx; border-radius: 11rpx; background: var(--divider); margin: 28rpx 4rpx 18rpx; }
.hot-sk-chart { height: 550rpx; border-radius: 12rpx; background: var(--divider); }
.featured-state { min-height: 180rpx; margin-bottom: 16rpx; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 18rpx; color: var(--text-sub); background: var(--card); border: 1rpx solid var(--card-border); border-radius: var(--radius); font-size: 22rpx; }
.featured-list-skeleton { margin-bottom: 8rpx; }
.featured-skeleton-row { display: flex; align-items: center; gap: 20rpx; min-height: 112rpx; padding: 12px; margin-bottom: 8px; }
.featured-sk-image { width: 56px; height: 56px; flex: 0 0 56px; border-radius: 10px; background: var(--divider); }
.featured-sk-copy { flex: 1; display: flex; flex-direction: column; gap: 14rpx; }
.featured-sk-copy view { width: 72%; height: 19rpx; border-radius: 10rpx; background: var(--divider); }
.featured-sk-copy view:last-child { width: 48%; }
.featured-sk-price { width: 92rpx; height: 26rpx; border-radius: 13rpx; background: var(--divider); }

.asset-scroll { white-space: nowrap; margin-bottom: 8px; }
.arow-s { display: inline-flex; justify-content: space-between; align-items: center; width: 500rpx; padding: 16px; margin-right: 10px; vertical-align: top; }
.an { color: var(--text); font-size: 14px; font-weight: 700; display: block; }
.ag { color: var(--text-sub); font-size: 11px; margin-top: 4px; display: block; }
.ar { text-align: right; }
.av { font-size: 16px; font-weight: 800; font-variant-numeric: tabular-nums; }
.al2 { display: block; color: var(--text-sub); font-size: 10px; margin-top: 2px; }

.prow { display: flex; align-items: center; padding: 12px; margin-bottom: 8px; gap: 12px; }
.pimg { width: 56px; height: 56px; border-radius: 10px; background: var(--text-dim); flex-shrink: 0; }
.pl { flex: 1; min-width: 0; }
.pn { color: var(--text); font-size: 14px; font-weight: 700; display: block; }
.pm { color: var(--text-sub); font-size: 11px; margin-top: 3px; display: block; }
.pr { text-align: right; display: flex; flex-wrap: wrap; align-items: baseline; justify-content: flex-end; max-width: 118px; }
.pp { color: var(--primary); font-size: 17px; font-weight: 800; font-variant-numeric: tabular-nums; }
.pu { color: var(--text-sub); font-size: 10px; }
.p-buy { flex-basis: 100%; color: var(--primary); font-size: 10px; margin-top: 3px; }
</style>
