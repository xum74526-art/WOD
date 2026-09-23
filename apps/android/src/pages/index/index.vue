<template>
  <view v-if="userStore.authReady && userStore.isLogin" :class="['page', { 'page--modal-open': majorAnnouncement }]">
    <view class="shell" :style="{ paddingTop: 'calc(20rpx + var(--safe-top))' }">
      <view class="topbar">
        <view class="greeting">
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
        <text class="hero-val">{{ fmtCardHours(totalAsset) }}</text>
        <view class="hero-row">
          <view class="hero-sub">
            <text class="sub-label">{{ t('todayRealizedEarnings') }}</text>
            <text class="sub-val" :class="amountTone(rev?.today)">{{ signedCardHours(rev?.today) }} {{ t('cardHour') }}</text>
          </view>
          <view class="hero-sub">
            <text class="sub-label">{{ t('totalRealizedEarnings') }}</text>
            <text class="sub-val" :class="amountTone(rev?.total)">{{ signedCardHours(rev?.total, false) }} {{ t('cardHour') }}</text>
          </view>
        </view>
      </view>

      <HomePromoCarousel />

      <view class="divider"></view>

      <view v-if="homeLoadError" class="home-load-warning">
        <text>{{ t('partialAssetDataUnavailable') }}</text>
        <text class="home-load-retry" role="button" @tap="load">{{ t('retry') }}</text>
      </view>

      <scroll-view scroll-x class="price-bar" :show-scrollbar="false">
        <view class="pb-item pressable" v-for="p in hot" :key="p.id" @tap="go('/pages/product/detail?id=' + p.id)">
          <text class="pb-name">{{ p.gpu_model }}</text>
          <text class="pb-price">{{ productCardHourPrice(p) }} {{ t('cardHourPerGpuHour') }}</text>
          <text class="pb-change" :class="changeTone(modelChange(p))">{{ modelChangeText(p) }}</text>
        </view>
      </scroll-view>

      <view class="divider"></view>

      <view class="quick">
        <template v-if="commerce.directTradeEnabled">
          <view class="q-item pressable" @tap="go('/pages/wallet/index')">
            <view class="q-icon"><AppIcon name="wallet" :size="36" /></view>
            <view class="q-text"><text>{{ t('recharge') }}</text></view>
          </view>
          <view class="q-item pressable" @tap="go('/pages/wallet/index?withdraw=1')">
            <view class="q-icon"><AppIcon name="wallet" :size="36" /></view>
            <view class="q-text"><text>{{ t('withdraw') }}</text></view>
          </view>
        </template>
        <template v-else-if="commerce.matchmakingEnabled">
          <view class="q-item pressable" @tap="go('/pages/buy-request/index?compose=1')">
            <view class="q-icon"><AppIcon name="gpu" :size="36" /></view>
            <view class="q-text"><text>{{ t('submitRequirement') }}</text></view>
          </view>
          <view class="q-item pressable" @tap="go('/pages/buy-request/index')">
            <view class="q-icon"><AppIcon name="order" :size="36" /></view>
            <view class="q-text"><text>{{ t('myRequirements') }}</text></view>
          </view>
        </template>
        <template v-else>
          <view class="q-item pressable" @tap="go('/pages/quote/index')">
            <view class="q-icon"><AppIcon name="search" :size="36" /></view>
            <view class="q-text"><text>{{ t('viewMarket') }}</text></view>
          </view>
          <view class="q-item pressable" @tap="go('/pages/buy-request/index')">
            <view class="q-icon"><AppIcon name="order" :size="36" /></view>
            <view class="q-text"><text>{{ t('myRequirements') }}</text></view>
          </view>
        </template>
        <view class="q-item pressable" @tap="goTab('/pages/market/index')">
          <view class="q-icon"><AppIcon name="gpu" :size="36" /></view>
          <view class="q-text"><text>{{ t('buyCompute') }}</text></view>
        </view>
        <view class="q-item pressable" @tap="go('/pages/orders/index')">
          <view class="q-icon"><AppIcon name="order" :size="36" /></view>
          <view class="q-text"><text>{{ t('orders') }}</text></view>
        </view>
      </view>

      <SectionHeader :title="t('runningCompute')">
        <template #extra><text class="more" @tap="goTab('/pages/assets/index')">{{ t('all') }} ›</text></template>
      </SectionHeader>
      <view v-if="!assets.length" class="empty">{{ t("noRunning") }}</view>
      <scroll-view scroll-x class="asset-scroll" :show-scrollbar="false">
        <view v-for="a in assets" :key="a.id" class="card arow-s pressable" @tap="go('/pages/asset/detail?id=' + a.id)">
          <view class="al">
          <text class="an">{{ localizeProductName(a.product_name, i18n.lang) }}</text>
            <text class="ag">{{ a.gpu_model }} · {{ a.purchase_type === 'holding' ? t('holdingMode') : t('剩余 {days} 天', { days: a.remaining_days ?? 0 }) }}</text>
          </view>
          <view class="ar">
            <text class="av" :class="assetEarningsTone(a)">{{ assetEarningsAmount(a) }}</text>
            <text class="al2">{{ assetEarningsLabel(a) }}</text>
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
          <view class="hot-market-head pressable" @tap="goTrend(activeHotTrend)">
            <view>
              <text class="hot-model">{{ activeHotTrend.item.gpu_model }}</text>
              <text class="hot-variant">{{ activeHotTrend.item.gpu_variant || t('standardVariant') }}</text>
            </view>
            <view class="hot-market-value">
              <text class="hot-price">{{ activeHotTrend.item.median_price_cny == null ? '--' : `${fmtCHn(activeHotTrend.item.median_price_cny)} ${t('cardHourPerGpuHour')}` }}</text>
              <text class="hot-change" :class="changeTone(trendSevenDayChange(activeHotTrend))">{{ trendChangeText(activeHotTrend) }}</text>
              <text v-if="trendHasFullHistory(activeHotTrend)" class="hot-range">{{ priceRangeText(activeHotTrend.item) }}</text>
            </view>
          </view>
          <view class="hot-full-chart" @tap="retryActiveTrend">
            <view class="hot-chart-period">
              <text>{{ t('thirtyDays') }}</text>
              <text>{{ t('candlestickMode') }}</text>
            </view>
            <CandlestickChart
              :candles="activeHotTrend.candles?.candles || []"
              compact
              :source-note="historySourceText(activeHotTrend)"
              :history-state="marketHistoryDisplayState(activeHotTrend.candles)"
              :observed-days="marketObservedDayCount(activeHotTrend.candles)"
              :reference-price-cny="activeHotTrend.candles?.latest_live_price_cny ?? activeHotTrend.item.median_price_cny"
              :reference-comparable-to-history="activeHotTrend.candles?.latest_live_comparable_to_history === true"
              :reference-sample-count="activeHotTrend.item.sample_count"
              :reference-observed-at="activeHotTrend.candles?.latest_live_observed_at || ''"
              :bucket-seconds="activeHotTrend.candles?.bucket_seconds || 0"
              range="30d"
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
        <view v-for="p in hot" :key="p.id" class="card prow pressable" @tap="go('/pages/product/detail?id=' + p.id)">
          <image class="pimg" :src="productImage(p)" mode="aspectFill" lazy-load :fade-show="false" @error="markProductImageFailed(p.id)" />
          <view class="pl">
            <text class="pn">{{ localizeProductName(p.name, i18n.lang) }}</text>
            <text class="pm">{{ featuredProductMeta(p) }}</text>
          </view>
          <view class="pr">
            <template v-if="commerce.directTradeEnabled">
              <text class="pp">{{ fmtCardHours(directTradeCardHoursPerGpuHour(p)) }}</text>
              <text class="p-buy">{{ t(directTradeProductPurchasable(p) ? 'k_25575fc0' : 'viewDetail') }}</text>
            </template>
            <template v-else-if="commerce.matchmakingEnabled && p.inquiry_available !== false">
              <text class="pp">{{ t('inquiry') }}</text>
              <text class="pu">{{ t('inquiryContactHintShort') }}</text>
              <text class="p-buy">{{ t('submitRequirement') }}</text>
            </template>
            <template v-else>
              <text class="pp unavailable">{{ t('dataUnavailable') }}</text>
              <text class="p-buy">{{ t('viewDetail') }}</text>
            </template>
          </view>
        </view>
      </template>
    </view>

    <view v-if="majorAnnouncement" class="major-announcement-overlay" role="presentation">
      <view class="major-announcement-dialog" role="dialog" aria-modal="true" @tap.stop>
        <view class="major-announcement-header">
          <view class="major-announcement-rail"></view>
          <view class="major-announcement-heading">
            <text class="major-announcement-label">{{ t('majorAnnouncement') }}</text>
            <text class="major-announcement-title">{{ localizedMajorAnnouncementTitle }}</text>
          </view>
          <view class="major-announcement-close" role="button" :aria-label="t('dismissMajorAnnouncement')" @tap.stop="dismissMajorAnnouncement">×</view>
        </view>

        <view v-if="localizedMajorAnnouncementTime" class="major-announcement-time">
          <text>{{ t('majorAnnouncementPublishedAt') }}：{{ localizedMajorAnnouncementTime }}</text>
        </view>

        <scroll-view class="major-announcement-body" scroll-y :show-scrollbar="false">
          <text class="major-announcement-content">{{ localizedMajorAnnouncementContent }}</text>
          <view v-if="majorAnnouncement.action_url" class="major-announcement-action" role="button" @tap="openMajorAnnouncement">
            <text>{{ t('viewMajorAnnouncementDetails') }}</text>
            <text aria-hidden="true">›</text>
          </view>
        </scroll-view>

        <view class="major-announcement-footer">
          <view class="major-announcement-acknowledge" role="button" @tap="dismissMajorAnnouncement">
            <text>{{ t('acknowledgeMajorAnnouncement') }}</text>
          </view>
        </view>
      </view>
    </view>
  </view>
  <view v-else class="startup-gate" aria-busy="true">
    <image class="startup-logo" src="/static/logo/logo.png" mode="aspectFit" />
    <text class="startup-label">{{ t('loading') }}</text>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onHide, onShow, onUnload } from '@dcloudio/uni-app'
import { useUserStore } from '@/store/user'
import { useAssetStore } from '@/store/asset'
import { useNotificationStore } from '@/store/notification'
import { useCommerceStore } from '@/store/commerce'
import { getWallet } from '@/api/wallet'
import { getRevenueSummary, getRevenueChart } from '@/api/revenue'
import { getProducts } from '@/api/gpu'
import type { AssetItem } from '@/api/asset'
import { getMarketCandles, getMarketRanking, type MarketCandles, type MarketRankingItem } from '@/api/market'
import { getMajorAnnouncement, type MajorAnnouncement } from '@/api/notification'
import { fmtCHn, fmtCardHours, formatAmount, toCardHours } from '@/utils/format'
import { navigateTo as go, switchTab } from '@/utils/nav'
import type { Product } from '@/api/gpu'
import type { RevenueSummary, RevenuePoint } from '@/api/revenue'
import AppIcon from '@/components/AppIcon.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import Chart from '@/components/Chart.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import LanguageToggle from '@/components/LanguageToggle.vue'
import CandlestickChart from '@/components/CandlestickChart.vue'
import HomePromoCarousel from '@/components/HomePromoCarousel.vue'
import { useI18nStore } from '@/store/i18n'
import { localizePersonName, localizeProductName } from '@/utils/localize-content'
import { localizeRegionName } from '@/utils/region-name'
import { formatSignedMarketPercentNumber } from '@/utils/market-chart'
import { fallbackProductImage, resolveProductImage } from '@/utils/product-image'
import { directTradeCardHoursPerGpuHour, directTradeProductPurchasable } from '@/utils/direct-trade'
import {
  hasCompleteSevenDayMetric,
  selectFeaturedProducts,
  trustedSevenDayChange,
  trustedSevenDayPriceRange,
} from '@/utils/market-list'
import {
  historyProvenanceLabel,
  marketHistoryDisplayState,
  marketObservedDayCount,
} from '@/utils/market-history'
import {
  buildHomeTrendRequests,
  HOME_CANDLE_REFRESH_MS,
  HOME_RANKING_REFRESH_MS,
  HOME_TREND_LIMIT,
} from '@/utils/home-market-policy'

const userStore = useUserStore()
const assetStore = useAssetStore()
const notificationStore = useNotificationStore()
const commerce = useCommerceStore()
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
const majorAnnouncement = ref<MajorAnnouncement | null>(null)
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
let featuredProductsLoadedAt = 0

const totalAsset = computed(() => (assetStore.summary?.total_value ?? 0) + walletBalance.value)
const assets = computed(() => assetStore.summary?.items ?? [])
const activeHotTrend = computed(() => hotTrends.value[hotTrendIndex.value] || hotTrends.value[0] || null)
const notificationBadge = computed(() => notificationStore.unread > 99 ? '99+' : String(notificationStore.unread))
const localizedMajorAnnouncementTitle = computed(() => {
  const announcement = majorAnnouncement.value
  if (!announcement) return ''
  return i18n.lang === 'en' && announcement.title_en ? announcement.title_en : i18n.tr(announcement.title)
})
const localizedMajorAnnouncementContent = computed(() => {
  const announcement = majorAnnouncement.value
  if (!announcement) return ''
  return i18n.lang === 'en' && announcement.content_en ? announcement.content_en : i18n.tr(announcement.content)
})
const localizedMajorAnnouncementTime = computed(() => {
  const value = majorAnnouncement.value?.created_at
  if (!value) return ''
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) return value.replace('T', ' ').slice(0, 16)
  return date.toLocaleString(i18n.locale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
})

function majorAnnouncementDismissalKey() {
  return `kai-major-announcement-dismissed:v2:${user.value?.id || 'anonymous'}`
}

async function loadMajorAnnouncement() {
  try {
    const result = await getMajorAnnouncement(true)
    const dismissedId = Number(uni.getStorageSync(majorAnnouncementDismissalKey()))
    majorAnnouncement.value = result && dismissedId !== result.id ? result : null
  } catch {
    // Announcement availability must not block the authenticated home page.
  }
}

function dismissMajorAnnouncement() {
  if (!majorAnnouncement.value) return
  uni.setStorageSync(majorAnnouncementDismissalKey(), majorAnnouncement.value.id)
  majorAnnouncement.value = null
}

function openMajorAnnouncement() {
  const action = majorAnnouncement.value?.action_url
  go(action?.startsWith('/pages/') ? action : '/pages/notifications/index')
}

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
  if (productPool.value.length && Date.now() - featuredProductsLoadedAt < HOME_RANKING_REFRESH_MS) return
  if (!productPool.value.length) featuredLoading.value = true
  try {
    const response = await getProducts({ page_size: 100, market_source: 'kai', representative: true })
    productPool.value = response.items.filter((item) => item.market_source === 'kai')
    featuredProductsLoadedAt = Date.now()
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
    // KAI publishes one quote cohort every five minutes. Reuse the matching
    // ranking and candle cohort until the next publication window.
    if (!rankingLoadedAt || Date.now() - rankingLoadedAt >= HOME_RANKING_REFRESH_MS) {
      const ranking = await getMarketRanking(silent)
      const kaiRanking = ranking.items.filter((item) => item.sources.includes('kai'))
      volatilityMap.value = {}
      for (const item of kaiRanking) {
        const key = gpuKey(item.gpu_model, item.gpu_variant)
        const existing = volatilityMap.value[key]
        if (!existing || metricPriority(item) > metricPriority(existing)) {
          volatilityMap.value[key] = item
        }
      }
      updateHotProducts()
      const liveCandidates = kaiRanking
        .filter((item) => item.market_status === 'live' && item.median_price_cny != null && item.sample_count > 0)
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
    // Reuse current quote fields and the denser 30-day chart for this source
    // publication window.
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
          '30d',
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
  marketTimer = setInterval(() => loadHotMarket(true), HOME_RANKING_REFRESH_MS)
}

function productCardHourPrice(product: Pick<Product, 'price' | 'price_cny_per_gpu_hour' | 'price_card_hours_per_gpu_hour'>): string {
  const cny = Number(product.price_cny_per_gpu_hour ?? product.price ?? 0)
  return formatAmount(product.price_card_hours_per_gpu_hour ?? toCardHours(cny))
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

onShow(async () => {
  i18n.updateTabBar()
  await userStore.restore()
  if (!userStore.isLogin) { uni.reLaunch({ url: '/pages/login/index' }); return }
  Promise.all([load(), loadHotMarket(false)]).catch(() => {})
  loadMajorAnnouncement().catch(() => {})
  notificationStore.refresh(true).catch(() => {})
  startMarketTimer()
})
onHide(stopMarketTimer)
onUnload(stopMarketTimer)

function reload() { load() }
function goTab(url: string) { switchTab(url) }
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
  return hasCompleteSevenDayMetric(trend.item)
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
function amountTone(value: number | null | undefined): string {
  const amount = Number(value || 0)
  return amount > 0 ? 'up' : amount < 0 ? 'down' : ''
}
function signedCardHours(value: number | null | undefined, positiveSign = true): string {
  const amount = Number(value || 0)
  return `${positiveSign && amount > 0 ? '+' : ''}${fmtCardHours(amount)}`
}
function assetEarningsAmount(asset: AssetItem): string {
  const amount = Number(asset.purchase_type === 'holding' ? asset.pnl : asset.rebate_amount) || 0
  return `${amount > 0 ? '+' : ''}${fmtCardHours(amount)}`
}
function assetEarningsLabel(asset: AssetItem): string {
  return t(asset.purchase_type === 'holding' ? 'pnl' : 'rebateInfo')
}
function assetEarningsTone(asset: AssetItem): string {
  const amount = Number(asset.purchase_type === 'holding' ? asset.pnl : asset.rebate_amount) || 0
  return amount > 0 ? 'up' : amount < 0 ? 'down' : ''
}
function featuredProductMeta(product: Product): string {
  const parts = [product.memory]
  if (product.region_name) parts.push(localizeRegionName(product.region_name, i18n.lang, product.region_code))
  if (Number.isFinite(Number(product.stock))) parts.push(t('countDevices', { count: Math.max(0, Math.floor(Number(product.stock))) }))
  return parts.filter(Boolean).join(' · ')
}
function compareHomeMarketCandidate(a: MarketRankingItem, b: MarketRankingItem): number {
  const aOfficial = /official/i.test(String(a.history_provenance?.kind || '')) ? 1 : 0
  const bOfficial = /official/i.test(String(b.history_provenance?.kind || '')) ? 1 : 0
  if (aOfficial !== bOfficial) return bOfficial - aOfficial
  const sampleDifference = Number(b.quote_sample_count ?? b.sample_count ?? 0)
    - Number(a.quote_sample_count ?? a.sample_count ?? 0)
  if (sampleDifference !== 0) return sampleDifference
  const aModel = gpuKey(a.gpu_model).split('|')[0]
  const bModel = gpuKey(b.gpu_model).split('|')[0]
  const a4090 = aModel === 'RTX4090' ? 1 : 0
  const b4090 = bModel === 'RTX4090' ? 1 : 0
  return b4090 - a4090
}
function historySourceText(trend: HotTrend): string {
  return historyProvenanceLabel(trend.candles?.provenance || trend.item.history_provenance, t)
    || t('kaiPricingSource')
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
.page {
  min-height: 100vh;
  background: var(--bg);
  --card: var(--home-card);
  --bg-2: var(--home-card-soft);
  --card-border: var(--home-card-border);
  --shadow: var(--home-card-shadow);
}
.page--modal-open { height: 100vh; overflow: hidden; }
.startup-gate { min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 18rpx; background: var(--bg); color: var(--text-sub); }
.startup-logo { width: 112rpx; height: 112rpx; border-radius: 28rpx; }
.startup-label { font-size: 24rpx; }
.shell { padding: 0 20px calc(132rpx + var(--safe-bottom)); }

.topbar { position: relative; z-index: 2; display: flex; justify-content: space-between; align-items: center; min-height: 88rpx; padding: 8rpx 0 20rpx; }
.greeting { min-width: 0; flex: 1; display: flex; align-items: baseline; gap: 4rpx; padding-right: 8rpx; }
.hi { flex-shrink: 0; color: var(--text-sub); font-size: 13px; }
.uname { min-width: 0; overflow: hidden; color: var(--text); font-size: 15px; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.top-actions { flex-shrink: 0; display: flex; gap: 6px; align-items: center; color: var(--text-sub); }
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

.major-announcement-overlay { position: fixed; inset: 0; z-index: 1000; padding: calc(28rpx + var(--safe-top)) 28rpx calc(28rpx + var(--safe-bottom)); box-sizing: border-box; background: rgba(4, 20, 22, 0.62); display: flex; align-items: center; justify-content: center; }
.major-announcement-dialog { width: 100%; max-width: 680rpx; max-height: calc(100vh - 56rpx - var(--safe-top) - var(--safe-bottom)); overflow: hidden; box-sizing: border-box; border: 1rpx solid var(--border); border-radius: 32rpx; background: var(--card); box-shadow: 0 34rpx 100rpx rgba(0, 24, 26, 0.34); display: flex; flex-direction: column; }
.major-announcement-header { position: relative; flex: 0 0 auto; padding: 42rpx 88rpx 26rpx 38rpx; display: flex; align-items: flex-start; gap: 20rpx; }
.major-announcement-rail { width: 7rpx; height: 68rpx; flex: 0 0 7rpx; border-radius: 4rpx; background: var(--primary); }
.major-announcement-heading { min-width: 0; flex: 1; }
.major-announcement-label { display: block; color: var(--primary); font-size: 19rpx; font-weight: 700; letter-spacing: 3rpx; }
.major-announcement-title { display: block; margin-top: 8rpx; color: var(--text); font-size: 34rpx; font-weight: 750; line-height: 1.35; }
.major-announcement-close { position: absolute; top: 25rpx; right: 23rpx; width: 62rpx; height: 62rpx; border-radius: 18rpx; color: var(--text-dim); font-size: 45rpx; font-weight: 300; line-height: 58rpx; text-align: center; }
.major-announcement-close:active { color: var(--text); background: var(--bg-2); }
.major-announcement-time { flex: 0 0 auto; margin: 0 38rpx; padding: 0 0 24rpx 27rpx; border-bottom: 1rpx solid var(--divider); color: var(--text-sub); font-size: 22rpx; font-variant-numeric: tabular-nums; }
.major-announcement-body { min-height: 240rpx; height: 44vh; max-height: 680rpx; box-sizing: border-box; padding: 32rpx 38rpx; }
.major-announcement-content { display: block; color: var(--text); font-size: 28rpx; line-height: 1.85; white-space: pre-wrap; word-break: break-word; }
.major-announcement-action { width: fit-content; min-height: 72rpx; margin-top: 24rpx; color: var(--primary); display: flex; align-items: center; gap: 10rpx; font-size: 25rpx; font-weight: 700; }
.major-announcement-action:active { opacity: 0.72; }
.major-announcement-footer { flex: 0 0 auto; padding: 24rpx 38rpx 36rpx; border-top: 1rpx solid var(--divider); }
.major-announcement-acknowledge { min-height: 92rpx; border-radius: 24rpx; color: #fff; background: var(--primary); box-shadow: 0 18rpx 44rpx rgba(12, 160, 164, 0.24); display: flex; align-items: center; justify-content: center; font-size: 30rpx; font-weight: 750; }
.major-announcement-acknowledge:active { opacity: 0.86; transform: translateY(1rpx); }

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
.q-item { min-width: 0; min-height: 102px; flex: 1; display: flex; flex-direction: column; align-items: center; box-sizing: border-box; padding: 14px 4px 12px; background: var(--card); border: 1px solid var(--card-border); border-radius: var(--radius); }
.q-icon { flex: 0 0 36px; margin-bottom: 6px; color: var(--primary); width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; background: var(--primary-soft); }
.q-text { width: 100%; min-height: 30px; display: flex; align-items: center; justify-content: center; color: var(--text); font-size: 11px; line-height: 1.25; overflow-wrap: break-word; text-align: center; }

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
.hot-chart-period { display: flex; align-items: center; gap: 10rpx; padding: 12rpx 8rpx 2rpx; color: var(--text-dim); font-size: 17rpx; font-weight: 650; }
.hot-chart-period text:first-child { color: var(--primary); }
.hot-market-empty { padding: 38rpx 20rpx; color: var(--text-sub); text-align: center; font-size: 22rpx; display: flex; flex-direction: column; align-items: center; gap: 18rpx; }
.hot-market-retry { min-height: 64rpx; padding: 0 26rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: var(--radius); font-weight: 700; }
.hot-market-skeleton { padding: 10rpx 20rpx 24rpx; }
.hot-sk-tabs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12rpx; }
.hot-sk-tabs view { height: 48rpx; border-radius: 10rpx; background: var(--divider); }
.hot-sk-head { width: 44%; height: 22rpx; border-radius: 11rpx; background: var(--divider); margin: 28rpx 4rpx 18rpx; }
.hot-sk-chart { height: 280rpx; border-radius: 12rpx; background: var(--divider); }
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
