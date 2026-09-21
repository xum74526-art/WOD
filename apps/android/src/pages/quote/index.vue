<template>
  <view class="page">
    <AppNavBar :title="t('computeMarket')" />
    <view class="shell">
      <SegmentedControl :items="tabs" :model-value="tab" @update:model-value="onTab" />

      <template v-if="tab === 0">
        <view class="status-line">
          <view class="freshness" :class="overallStatus">
            <view class="status-mark"></view>
            <text>{{ statusText(overallStatus) }}</text>
          </view>
          <text class="refresh-text">{{ t('refreshCountdown', { seconds: refreshIn }) }}</text>
        </view>

        <scroll-view v-if="models.length" scroll-x class="model-scroll" :show-scrollbar="false">
          <view
            v-for="item in models"
            :key="modelKey(item)"
            class="model-chip"
            :class="{ active: selectedKey === modelKey(item) }"
            @tap="selectModel(item)"
          >
            <text class="model-name">{{ item.gpu_model }}</text>
            <text v-if="item.gpu_variant" class="model-variant">{{ item.gpu_variant }}</text>
          </view>
        </scroll-view>

        <view v-if="initialLoading" class="market-skeleton">
          <view class="sk-line wide"></view>
          <view class="sk-line price"></view>
          <view class="sk-chart"></view>
        </view>

        <view v-else-if="initialError && !models.length" class="empty-state">
          <text class="empty-title">{{ t('marketLoadFailed') }}</text>
          <text class="retry-link" role="button" @tap="loadBase">{{ t('retry') }}</text>
        </view>

        <view v-else-if="!models.length" class="empty-state">
          <text class="empty-title">{{ t('noVerifiedMarketData') }}</text>
          <text class="empty-copy">{{ statusText(overallStatus) }}</text>
        </view>

        <template v-else>
          <view class="price-summary">
            <view class="summary-head">
              <view>
                <text class="gpu-title">{{ currentModel?.gpu_model }}</text>
                <text class="gpu-sub">{{ currentModel?.gpu_variant || t('standardVariant') }}</text>
                <text v-if="selectedMetric" class="gpu-volatility" :class="changeTone(selectedSevenDayChange)">{{ selectedHistoryHeadline }}</text>
                <text v-if="selectedMetric && chartHistoryState === 'full'" class="gpu-range">{{ priceRangeText(selectedMetric) }}</text>
              </view>
              <text class="updated-at">{{ t('lastUpdated') }} {{ lastUpdated }}</text>
            </view>
            <view class="price-comparison">
              <view class="comparison-price low-price">
                <text class="comparison-label">{{ t('lowestPrice') }}</text>
                <view class="comparison-value-row">
                  <text v-if="latest?.summary.min_price_cny != null" class="comparison-value">¥{{ cnyNumber(latest.summary.min_price_cny) }}</text>
                  <text v-else class="comparison-value muted">--</text>
                  <text class="comparison-unit">{{ t('perGpuHour') }}</text>
                </view>
              </view>
              <view class="comparison-divider"></view>
              <view class="comparison-price high-price">
                <text class="comparison-label">{{ t('highestPrice') }}</text>
                <view class="comparison-value-row">
                  <text v-if="latest?.summary.max_price_cny != null" class="comparison-value">¥{{ cnyNumber(latest.summary.max_price_cny) }}</text>
                  <text v-else class="comparison-value muted">--</text>
                  <text class="comparison-unit">{{ t('perGpuHour') }}</text>
                </view>
              </view>
              <text v-if="selectedSevenDayChange != null" class="change" :class="changeTone(selectedSevenDayChange)">
                {{ selectedHistoryHeadline }}
              </text>
              <text v-else class="change neutral">{{ chartStateSummary }}</text>
            </view>
            <view class="summary-stats">
              <view class="metric">
                <text class="metric-value">{{ latest?.summary.sample_count || 0 }}</text>
                <text class="metric-label">{{ t('quoteSamples') }}</text>
              </view>
              <view class="metric">
                <text class="metric-value source-metric">{{ t('kaiPricingSource') }}</text>
                <text class="metric-label">{{ t('currentMarketSource') }}</text>
              </view>
            </view>
          </view>

          <view class="source-context">
            <view class="source-context-main">
              <text class="source-context-name">{{ t('kaiPricingSource') }}</text>
              <text class="source-context-copy">{{ t('kaiOnlyMarketHint') }}</text>
            </view>
            <text class="source-context-state" :class="overallStatus">{{ statusText(overallStatus) }}</text>
          </view>

          <view class="chart-section">
            <view class="range-row">
              <view
                v-for="item in ranges"
                :key="item.key"
                class="range-item"
                :class="{ active: timeRange === item.key }"
                @tap="selectRange(item.key)"
              >{{ item.label }}</view>
            </view>
            <CandlestickChart
              :key="selectedKey + ':' + timeRange"
              :candles="displayedCandles"
              :source-note="historySourceText"
              :loading="refreshing && !candles"
              :error="candleLoadError && !candles"
              :history-state="chartHistoryState"
              :observed-days="chartObservedDays"
              :reference-price-cny="candles?.latest_live_price_cny ?? latest?.summary.median_price_cny"
              :reference-comparable-to-history="candles?.latest_live_comparable_to_history === true"
              :reference-sample-count="latest?.summary.sample_count || 0"
              :reference-observed-at="candles?.latest_live_observed_at || latestObservedAt"
              :bucket-seconds="candles?.bucket_seconds || 0"
              :range="timeRange"
              display-currency="CNY"
              zoomable
            />
          </view>

          <view class="range-summary">
            <view class="range-cell">
              <text class="range-label">{{ t('lowestPrice') }}</text>
              <text class="range-value">{{ cnyPricePerGpuHour(candleStats.low) }}</text>
            </view>
            <view class="range-cell center">
              <text class="range-label">{{ t('priceSpread') }}</text>
              <text class="range-value primary">{{ cnyPricePerGpuHour(candleStats.spread) }}</text>
            </view>
            <view class="range-cell">
              <text class="range-label">{{ t('highestPrice') }}</text>
              <text class="range-value">{{ cnyPricePerGpuHour(candleStats.high) }}</text>
            </view>
          </view>

          <view class="source-details">
            <view v-for="item in kaiSnapshots" :key="item.source" class="source-row">
              <view class="source-main">
                <text class="source-name">{{ marketSourceDisplayName(item.source, t, item.source_name) }}</text>
                <text class="source-meta">{{ t('sampleCount', { count: item.sample_count }) }} · {{ sourceChecked(item) }}</text>
              </view>
              <view class="source-price">
                <view class="source-band">
                  <text class="source-low">{{ t('lowPriceShort') }} {{ cnyPricePerGpuHour(item.min_price_cny) }}</text>
                  <text class="source-high">{{ t('highPriceShort') }} {{ cnyPricePerGpuHour(item.max_price_cny) }}</text>
                </view>
                <text class="source-original">{{ originalPrice(item) }}</text>
              </view>
            </view>
          </view>

          <view class="market-link" @tap="goMarket">
            <view>
              <text class="link-title">{{ t('viewKaiComputeOffers') }}</text>
              <text class="link-copy">{{ t('kaiMarketCatalogHint') }}</text>
            </view>
            <text class="link-arrow">›</text>
          </view>

          <view class="data-note">
            <text class="note-title">{{ t('dataMethod') }}</text>
            <text class="note-copy">{{ t('marketMethodHint') }}</text>
          </view>
        </template>
      </template>

      <template v-else-if="tab === 1">
        <view v-if="rankingLoading && !ranking.length" class="list-skeleton">
          <view v-for="index in 4" :key="index" class="list-skeleton-row"><view class="sk-rank"></view><view class="sk-copy"></view><view class="sk-value"></view></view>
        </view>
        <view v-else-if="rankingError && !ranking.length" class="empty-state">
          <text class="empty-title">{{ t('rankingLoadFailed') }}</text>
          <text class="retry-link" role="button" @tap="refreshRanking(false)">{{ t('retry') }}</text>
        </view>
        <view v-else-if="!ranking.length" class="empty-state"><text class="empty-title">{{ t('noVerifiedMarketData') }}</text><text class="empty-copy">{{ t('kaiOnlyMarketHint') }}</text></view>
        <view v-for="(item, index) in ranking" :key="`${item.gpu_model}-${item.gpu_variant}`" class="ranking-row" @tap="openTrend(item)">
          <text class="rank">{{ index + 1 }}</text>
          <view class="rank-main">
            <text class="rank-name">{{ item.gpu_model }} {{ item.gpu_variant }}</text>
            <text class="rank-meta">{{ t('quoteSampleCount', { count: rankingSampleCount(item) }) }} · {{ t('coveredRegions', { count: item.region_count || 0 }) }} · {{ statusText(item.market_status) }}</text>
            <text class="rank-range">{{ t('lowHighRange', { low: cnyPriceOrDash(item.min_price_cny ?? item.range_low_cny), high: cnyPriceOrDash(item.max_price_cny ?? item.range_high_cny) }) }}{{ t('perGpuHour') }}</text>
          </view>
          <view class="rank-price">
            <text class="rank-label">{{ t('medianPrice') }}</text>
            <text class="rank-value">{{ cnyPriceOrDash(item.median_price_cny) }}</text>
            <text class="rank-unit">{{ t('perGpuHour') }}</text>
            <text class="rank-volatility" :class="changeTone(sevenDayChange(item))">{{ changeText(item) }}</text>
          </view>
        </view>
      </template>

      <template v-else>
        <scroll-view v-if="models.length" scroll-x class="model-scroll regional-model-scroll" :show-scrollbar="false">
          <view
            v-for="item in models"
            :key="modelKey(item)"
            class="model-chip"
            :class="{ active: selectedKey === modelKey(item) }"
            @tap="selectRegionalModel(item)"
          >
            <text class="model-name">{{ item.gpu_model }}</text>
            <text v-if="item.gpu_variant" class="model-variant">{{ item.gpu_variant }}</text>
          </view>
        </scroll-view>
        <view v-if="regionalIdentity" class="regional-context">
          <view>
            <text class="regional-context-title">{{ regionalIdentity }}</text>
            <text class="regional-context-copy">{{ t('sameModelRegionalComparison') }}</text>
          </view>
          <view class="regional-context-stats">
            <text class="regional-context-count">{{ t('coveredRegions', { count: regionalMeta?.region_count || regions.length }) }}</text>
            <text class="regional-context-status" :class="regionalMeta?.market_status || overallStatus">{{ statusText(regionalMeta?.market_status || overallStatus) }}</text>
          </view>
        </view>
        <view v-if="regionsLoading && !regions.length" class="list-skeleton">
          <view v-for="index in 4" :key="index" class="list-skeleton-row"><view class="sk-copy"></view><view class="sk-value"></view></view>
        </view>
        <view v-else-if="regionsError && !regions.length" class="empty-state">
          <text class="empty-title">{{ t('regionalLoadFailed') }}</text>
          <text class="retry-link" role="button" @tap="loadRegions(false)">{{ t('retry') }}</text>
        </view>
        <view v-else-if="!regions.length" class="empty-state"><text class="empty-title">{{ t('noRegionalQuotes') }}</text><text class="empty-copy">{{ t('sameModelRegionalComparison') }}</text></view>
        <view v-for="item in regions" :key="item.region_code || item.region" class="region-row" :class="{ cheapest: item.is_lowest }">
          <view class="region-main">
            <view class="region-title-row">
              <text class="region-name">{{ localizeRegionName(item.region, i18n.lang, item.region_code) }}</text>
              <text v-if="item.is_lowest" class="lowest-badge">{{ t('lowestRegion') }}</text>
            </view>
            <text class="region-meta">{{ t('quoteSampleCount', { count: item.quote_sample_count || 0 }) }} · {{ t('quoteLocations', { count: item.location_count || 0 }) }}</text>
            <text class="region-range">{{ t('lowHighRange', { low: cnyPriceOrDash(item.min_price_cny), high: cnyPriceOrDash(item.max_price_cny) }) }}{{ t('perGpuHour') }}</text>
          </view>
          <view class="region-values">
            <text class="region-label">{{ t('medianPrice') }}</text>
            <text class="region-price">{{ cnyPriceOrDash(item.median_price_cny) }}</text>
            <text class="region-unit">{{ t('perGpuHour') }}</text>
            <text class="region-spread" :class="{ baseline: item.is_lowest }">{{ regionalSpreadText(item) }}</text>
          </view>
        </view>
        <view v-if="regions.length" class="data-note regional-note">
          <text class="note-title">{{ t('regionalDataMethod') }}</text>
          <text class="note-copy">{{ t('regionalMethodHint') }}</text>
        </view>
      </template>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { getRegionalQuotes, type RegionalQuoteItem, type RegionalQuoteResponse } from '@/api/gpu'
import {
  getLatestMarket,
  getMarketCandles,
  getMarketModels,
  getMarketRanking,
  getMarketSourceStatus,
  type LatestMarket,
  type MarketCandles,
  type MarketModel,
  type MarketQuoteRange,
  type MarketRankingItem,
  type MarketSnapshot,
  type MarketSourceState,
} from '@/api/market'
import AppNavBar from '@/components/AppNavBar.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import CandlestickChart from '@/components/CandlestickChart.vue'
import { switchTab } from '@/utils/nav'
import { useI18nStore } from '@/store/i18n'
import { formatNumber } from '@/utils/format'
import { localizeRegionName } from '@/utils/region-name'
import { formatSignedMarketPercentNumber } from '@/utils/market-chart'
import {
  hasCompleteSevenDayMetric,
  trustedSevenDayChange,
  trustedSevenDayPriceRange,
} from '@/utils/market-list'
import {
  historyProvenanceLabel,
  marketHistoryDisplayState,
  marketObservedDayCount,
  marketSourceDisplayName,
} from '@/utils/market-history'
import {
  latestMarketObservationMs,
  marketCandlesNeedRefresh,
  QUOTE_POLL_SECONDS,
} from '@/utils/market-polling'

const i18n = useI18nStore()
const { t } = i18n
const tab = ref(0)
const models = ref<MarketModel[]>([])
const ranking = ref<MarketRankingItem[]>([])
const latest = ref<LatestMarket | null>(null)
const candles = ref<MarketCandles | null>(null)
const sourceStates = ref<MarketSourceState[]>([])
const regions = ref<RegionalQuoteItem[]>([])
const regionalMeta = ref<RegionalQuoteResponse | null>(null)
const selectedKey = ref('')
const selectedSources = ref<string[]>(['kai'])
const timeRange = ref<MarketQuoteRange>('30d')
const refreshIn = ref(QUOTE_POLL_SECONDS)
const initialLoading = ref(true)
const initialError = ref(false)
const refreshing = ref(false)
const candleLoadError = ref(false)
const rankingLoading = ref(false)
const rankingError = ref(false)
const regionsLoading = ref(false)
const regionsError = ref(false)
const requestedModel = ref('')
const requestedVariant = ref('')
let timer: ReturnType<typeof setInterval> | null = null
let refreshGeneration = 0
let candlesLoadedAt = 0
let candleRequestKey = ''
let candleObservationCursor = 0
let sourceStatesLoadedAt = 0
let regionalGeneration = 0

const tabs = computed(() => [t('priceTrends'), t('modelRanking'), t('regionalPrices')])
const ranges = computed<Array<{ key: MarketQuoteRange; label: string }>>(() => [
  { key: '24h', label: t('twentyFourHours') },
  { key: '7d', label: t('sevenDays') },
  { key: '30d', label: t('thirtyDays') },
])
const currentModel = computed(() => models.value.find((item) => modelKey(item) === selectedKey.value) || models.value[0])
const regionalIdentity = computed(() => regionalMeta.value
  ? `${regionalMeta.value.gpu_model} ${regionalMeta.value.gpu_variant}`.trim()
  : currentModel.value
    ? `${currentModel.value.gpu_model} ${currentModel.value.gpu_variant}`.trim()
    : '')
const selectedRanking = computed(() => ranking.value.find((item) => item.gpu_model === currentModel.value?.gpu_model && item.gpu_variant === currentModel.value?.gpu_variant))
const selectedMetric = computed(() => selectedRanking.value || currentModel.value)
const displayedCandles = computed(() => {
  return candles.value?.candles || []
})
const chartHistoryState = computed(() => marketHistoryDisplayState(candles.value))
const chartObservedDays = computed(() => marketObservedDayCount(candles.value))
const chartStateSummary = computed(() => chartHistoryState.value === 'full'
  ? t('chartFullHistory')
  : chartHistoryState.value === 'partial'
    ? t('chartObservedDays', { days: chartObservedDays.value })
    : t('currentQuoteBaseline'))
const selectedSevenDayChange = computed(() => {
  // This headline is explicitly labelled as a seven-day metric. Never replace
  // it with the change of the currently selected chart range (for example 30d).
  return selectedMetric.value ? sevenDayChange(selectedMetric.value) : null
})
const selectedHistoryHeadline = computed(() => selectedSevenDayChange.value == null
  ? chartStateSummary.value
  : t('sevenDayChangeValue', { value: formatSignedMarketPercentNumber(selectedSevenDayChange.value) }))
const historySourceText = computed(() => historyProvenanceLabel(candles.value?.provenance || selectedMetric.value?.history_provenance, t))
const overallStatus = computed(() => {
  const states = sourceStates.value.filter((item) => selectedSources.value.includes(item.source)).map((item) => item.status)
  if (!states.length) return 'pending'
  if (states.every((state) => state === 'live')) return 'live'
  if (states.some((state) => state === 'unavailable')) return 'unavailable'
  if (states.some((state) => state === 'stale')) return 'stale'
  return 'delayed'
})
const lastUpdated = computed(() => {
  const dates = (latest.value?.items || []).map((item) => item.source_checked_at).filter(Boolean).map((value) => new Date(value as string).getTime())
  if (!dates.length) return '--'
  return new Date(Math.max(...dates)).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
})
const kaiSnapshots = computed(() => (latest.value?.items || []).filter((item) => item.source === 'kai'))
const latestObservedAt = computed(() => {
  const values = (latest.value?.items || [])
    .map((item) => item.observed_at || item.source_checked_at)
    .filter(Boolean)
    .map((value) => ({ value: String(value), time: new Date(String(value)).getTime() }))
    .filter((item) => Number.isFinite(item.time))
    .sort((a, b) => b.time - a.time)
  return values[0]?.value || ''
})
const candleStats = computed(() => {
  const rows = displayedCandles.value
  if (!rows.length) return { low: null, high: null, spread: null }
  const low = Math.min(...rows.map((item) => item.low_price_cny))
  const high = Math.max(...rows.map((item) => item.high_price_cny))
  return {
    low,
    high,
    spread: Math.max(0, high - low),
  }
})

function modelKey(item: Pick<MarketModel, 'gpu_model' | 'gpu_variant'>) { return `${item.gpu_model}|${item.gpu_variant || ''}` }
function cnyNumber(value: number) { return formatNumber(value) }
function cnyPriceOrDash(value?: number | null) { return value == null ? '--' : `¥${formatNumber(value)}` }
function cnyPricePerGpuHour(value?: number | null) {
  return value == null ? '--' : `${cnyPriceOrDash(value)}${t('perGpuHour')}`
}
function originalPrice(item: MarketSnapshot) {
  const suffix = item.currency === 'USD' && item.fx_date ? ` · ${item.fx_date}` : ''
  return `${formatNumber(item.min_price)}-${formatNumber(item.max_price)} ${item.currency}${suffix}`
}
function sourceChecked(item: MarketSnapshot) {
  if (!item.source_checked_at) return t('notUpdated')
  return new Date(item.source_checked_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
function statusText(status: string) {
  const map: Record<string, string> = { live: 'liveData', delayed: 'delayedData', stale: 'staleData', unavailable: 'sourceUnavailable', pending: 'sourcePending' }
  return t(map[status] || 'sourcePending')
}

function prioritizeRanking(items: MarketRankingItem[]) {
  return items.filter((item) => item.sources.includes('kai')).sort((a, b) => {
    const regionCoverage = Number(b.region_count || 0) - Number(a.region_count || 0)
    if (regionCoverage) return regionCoverage
    const samples = rankingSampleCount(b) - rankingSampleCount(a)
    if (samples) return samples
    return Number(b.history_day_count || 0) - Number(a.history_day_count || 0)
  })
}

function prioritizeModels(items: MarketModel[]) {
  return items.filter((item) => item.sources.includes('kai')).sort((a, b) => {
    const aComplete = hasCompleteSevenDayMetric(a) ? 1 : 0
    const bComplete = hasCompleteSevenDayMetric(b) ? 1 : 0
    if (aComplete !== bComplete) return bComplete - aComplete
    const a4090 = a.gpu_model.replace(/\s+/g, '').toUpperCase() === 'RTX4090' ? 1 : 0
    const b4090 = b.gpu_model.replace(/\s+/g, '').toUpperCase() === 'RTX4090' ? 1 : 0
    if (a4090 !== b4090) return b4090 - a4090
    return b.sample_count - a.sample_count
  })
}
function rankingSampleCount(item: MarketRankingItem): number {
  return Number(item.quote_sample_count ?? item.sample_count ?? 0)
}
function regionalSpreadText(item: RegionalQuoteItem): string {
  if (item.is_lowest) return t('lowestRegionBaseline')
  if (item.relative_to_lowest_pct == null) return t('notEnoughHistory')
  const value = Number(item.relative_to_lowest_pct)
  return Number.isFinite(value)
    ? t('relativeToLowest', { value: formatSignedMarketPercentNumber(value) })
    : t('notEnoughHistory')
}

function sevenDayChange(item: Pick<MarketRankingItem, 'change_7d_pct' | 'range_low_cny' | 'range_high_cny' | 'history_day_count' | 'history_span_hours'> | MarketModel): number | null {
  return hasCompleteSevenDayMetric(item) ? trustedSevenDayChange(item) : null
}
function changeText(item: Pick<MarketRankingItem, 'change_7d_pct' | 'range_low_cny' | 'range_high_cny' | 'history_day_count' | 'history_span_hours'> | MarketModel): string {
  const value = sevenDayChange(item)
  return value == null
    ? (Number(item.history_day_count || 0) > 1 ? t('chartObservedDays', { days: item.history_day_count }) : t('currentQuoteBaseline'))
    : t('sevenDayChangeValue', { value: formatSignedMarketPercentNumber(value) })
}
function priceRangeText(item: Pick<MarketRankingItem, 'change_7d_pct' | 'range_low_cny' | 'range_high_cny' | 'history_day_count' | 'history_span_hours'> | MarketModel): string {
  const range = hasCompleteSevenDayMetric(item) ? trustedSevenDayPriceRange(item) : null
  return range
    ? t('sevenDayPriceRangeCnyValue', { low: formatNumber(range.low), high: formatNumber(range.high) })
    : (Number(item.history_day_count || 0) > 1 ? t('chartObservedDays', { days: item.history_day_count }) : t('currentQuoteBaseline'))
}
function changeTone(value: number | null): string {
  return value == null || value === 0 ? 'neutral' : value > 0 ? 'rise' : 'fall'
}

async function loadBase() {
  const hasExistingModels = models.value.length > 0
  if (!hasExistingModels) initialLoading.value = true
  initialError.value = false
  try {
    const [modelResult, statusResult] = await Promise.allSettled([
      getMarketModels(),
      getMarketSourceStatus(),
    ])
    if (modelResult.status === 'rejected') {
      initialError.value = true
      return
    }
    models.value = prioritizeModels(modelResult.value.items)
    if (statusResult.status === 'fulfilled') {
      sourceStates.value = statusResult.value.items.filter((item) => item.source === 'kai')
      sourceStatesLoadedAt = Date.now()
    }
    if (!selectedKey.value && requestedModel.value) {
      const requested = models.value.find((item) => item.gpu_model === requestedModel.value && (!requestedVariant.value || item.gpu_variant === requestedVariant.value))
      if (requested) selectedKey.value = modelKey(requested)
    }
    if (!selectedKey.value && models.value.length) selectedKey.value = modelKey(models.value[0])
    if (currentModel.value) {
      selectedSources.value = ['kai']
      await refreshPrices(hasExistingModels, !candles.value)
    }
    // Ranking includes the heavier seven-day comparison. It is useful for the
    // ranking tab, but must not block the current price and K-line card.
    void refreshRanking(true)
  } catch {
    initialError.value = true
  } finally {
    initialLoading.value = false
  }
}

async function refreshRanking(silent = true) {
  rankingLoading.value = true
  rankingError.value = false
  try {
    ranking.value = prioritizeRanking((await getMarketRanking(silent)).items)
  } catch {
    rankingError.value = true
  } finally {
    rankingLoading.value = false
  }
}

async function refreshPrices(silent = true, forceHistory = false) {
  if (!currentModel.value || !selectedSources.value.length) return
  const generation = ++refreshGeneration
  const model = currentModel.value
  const sources = [...selectedSources.value]
  const range = timeRange.value
  const billingMode = 'ondemand'
  const historyKey = `${model.gpu_model}|${model.gpu_variant}|${range}|${[...sources].sort().join(',')}|${billingMode}`
  const historyRefreshMs = range === '7d' || range === '30d' ? 5 * 60_000 : 30_000
  const needsSourceState = !sourceStates.value.length || Date.now() - sourceStatesLoadedAt >= 30_000
  const needsHistory = forceHistory
    || !candles.value
    || candleRequestKey !== historyKey
    || Date.now() - candlesLoadedAt >= historyRefreshMs
  refreshing.value = true
  try {
    const [latestResult, stateResult, candleResult] = await Promise.allSettled([
      getLatestMarket(model.gpu_model, model.gpu_variant, sources, silent),
      needsSourceState
        ? getMarketSourceStatus(silent)
        : Promise.resolve({ server_time: '', items: sourceStates.value }),
      needsHistory
        ? getMarketCandles(model.gpu_model, model.gpu_variant, range, sources, silent, billingMode)
        : Promise.resolve(candles.value),
    ])
    // A model/source/range switch may happen while the previous request is in
    // flight. Only the latest selection is allowed to update the screen.
    if (generation !== refreshGeneration) return
    if (latestResult.status === 'rejected') throw latestResult.reason
    const nextLatest = latestResult.value
    const currentObservationMs = latestMarketObservationMs(nextLatest.items)
    latest.value = nextLatest
    let nextCandles = candleResult.status === 'fulfilled' ? candleResult.value : null
    let historyRefreshed = needsHistory && candleResult.status === 'fulfilled'
    let candleRefreshFailed = false
    if (marketCandlesNeedRefresh(
      candleObservationCursor,
      nextLatest.items,
      nextCandles?.latest_live_observed_at,
    )) {
      try {
        nextCandles = await getMarketCandles(
          model.gpu_model,
          model.gpu_variant,
          range,
          sources,
          silent,
          billingMode,
          { force_refresh: true },
        )
        historyRefreshed = true
      } catch {
        // Preserve the last verified chart and retry on the next refresh.
        candleRefreshFailed = true
      }
    }
    if (generation !== refreshGeneration) return
    if (nextCandles) {
      candles.value = nextCandles
      candleLoadError.value = false
      if (historyRefreshed) {
        candleRequestKey = historyKey
        candlesLoadedAt = Date.now()
      }
    } else if (needsHistory && !candles.value) {
      candleLoadError.value = true
    }
    if (stateResult.status === 'fulfilled') {
      sourceStates.value = stateResult.value.items
      if (needsSourceState) sourceStatesLoadedAt = Date.now()
    }
    if (!candleRefreshFailed && currentObservationMs > candleObservationCursor) {
      candleObservationCursor = currentObservationMs
    }
    refreshIn.value = QUOTE_POLL_SECONDS
  } catch {
    if (generation === refreshGeneration) refreshIn.value = QUOTE_POLL_SECONDS
  } finally {
    if (generation === refreshGeneration) refreshing.value = false
  }
}

async function loadRegions(_silent = true) {
  if (!currentModel.value) return
  const generation = ++regionalGeneration
  const model = currentModel.value
  regionsLoading.value = true
  regionsError.value = false
  try {
    const data = await getRegionalQuotes(model.gpu_model, model.gpu_variant || '')
    if (generation !== regionalGeneration) return
    regionalMeta.value = data
    regions.value = data.regions
  } catch {
    if (generation === regionalGeneration) regionsError.value = true
  } finally {
    if (generation === regionalGeneration) regionsLoading.value = false
  }
}

function startTimer() {
  stopTimer()
  timer = setInterval(() => {
    if (typeof document !== 'undefined' && document.hidden) return
    refreshIn.value -= 1
    if (refreshIn.value <= 0) {
      refreshIn.value = QUOTE_POLL_SECONDS
      if (!refreshing.value) void refreshPrices(true)
    }
  }, 1000)
}
function stopTimer() { if (timer) { clearInterval(timer); timer = null } }
async function onTab(value: number) {
  tab.value = value
  if ((value === 0 || value === 2) && !models.value.length) await loadBase()
  if (value === 1 && !ranking.value.length) await refreshRanking(false)
  if (value === 0 && currentModel.value && !latest.value) await refreshPrices(false, true)
  if (value === 2 && (!regionalMeta.value || regionalIdentity.value !== `${currentModel.value?.gpu_model || ''} ${currentModel.value?.gpu_variant || ''}`.trim())) await loadRegions()
}
async function selectModel(item: MarketModel) {
  selectedKey.value = modelKey(item)
  selectedSources.value = ['kai']
  latest.value = null
  candles.value = null
  candleObservationCursor = 0
  regions.value = []
  regionalMeta.value = null
  candleLoadError.value = false
  await refreshPrices(false, true)
}
async function selectRegionalModel(item: MarketModel) {
  if (selectedKey.value === modelKey(item) && regions.value.length) return
  selectedKey.value = modelKey(item)
  latest.value = null
  candles.value = null
  regions.value = []
  regionalMeta.value = null
  await loadRegions(false)
}
async function selectRange(value: MarketQuoteRange) { timeRange.value = value; await refreshPrices(false, true) }
function openTrend(item: MarketRankingItem) {
  const found = models.value.find((model) => model.gpu_model === item.gpu_model && model.gpu_variant === item.gpu_variant)
  if (found) selectModel(found)
  tab.value = 0
}
function goMarket() {
  if (currentModel.value) uni.setStorageSync('wod-market-keyword', currentModel.value.gpu_model)
  switchTab('/pages/market/index')
}

onLoad((options) => {
  requestedModel.value = options?.model ? decodeURIComponent(String(options.model)) : ''
  requestedVariant.value = options?.variant ? decodeURIComponent(String(options.variant)) : ''
})
onShow(async () => {
  i18n.updateTabBar()
  if (!models.value.length) await loadBase()
  else {
    void refreshPrices(true)
    if (!ranking.value.length) void refreshRanking(true)
  }
  startTimer()
})
onHide(stopTimer)
onUnload(stopTimer)
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.status-line { display: flex; align-items: center; justify-content: space-between; margin: 22rpx 2rpx 18rpx; }
.freshness { display: flex; align-items: center; gap: 10rpx; color: var(--text-sub); font-size: 22rpx; }
.status-mark { width: 14rpx; height: 14rpx; border-radius: 50%; background: var(--text-dim); }
.freshness.live { color: var(--up); }
.freshness.live .status-mark { background: var(--up); }
.freshness.delayed, .freshness.stale { color: #b7791f; }
.freshness.delayed .status-mark, .freshness.stale .status-mark { background: #b7791f; }
.freshness.unavailable { color: var(--down); }
.freshness.unavailable .status-mark { background: var(--down); }
.refresh-text { color: var(--text-dim); font-size: 22rpx; }
.model-scroll { white-space: nowrap; margin-bottom: 20rpx; }
.model-chip { display: inline-flex; align-items: baseline; gap: 8rpx; padding: 14rpx 22rpx; margin-right: 12rpx; border: 1rpx solid var(--border); border-radius: 14rpx; background: var(--card); color: var(--text-sub); }
.model-chip.active { color: var(--primary); border-color: var(--primary); background: var(--primary-soft); }
.model-name { font-size: 25rpx; font-weight: 650; }
.model-variant { font-size: 20rpx; opacity: 0.76; }
.price-summary, .chart-section, .source-details, .market-link, .data-note, .market-skeleton, .empty-state { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }
.price-summary { padding: 30rpx; }
.summary-head { display: flex; justify-content: space-between; align-items: flex-start; }
.gpu-title { display: block; color: var(--text); font-size: 32rpx; font-weight: 750; }
.gpu-sub { display: block; color: var(--text-sub); font-size: 21rpx; margin-top: 5rpx; }
.gpu-volatility { display: block; color: var(--primary); font-size: 20rpx; margin-top: 5rpx; font-variant-numeric: tabular-nums; }
.gpu-volatility.rise, .change.rise, .rank-volatility.rise { color: #C9363E; }
.gpu-volatility.fall, .change.fall, .rank-volatility.fall { color: #168A5B; }
.gpu-range { display: block; color: var(--text-sub); font-size: 19rpx; margin-top: 4rpx; font-variant-numeric: tabular-nums; }
.updated-at { color: var(--text-dim); font-size: 20rpx; }
.price-comparison { display: grid; grid-template-columns: minmax(0, 1fr) 1rpx minmax(0, 1fr); align-items: stretch; gap: 20rpx; margin: 24rpx 0 26rpx; }
.comparison-price { min-width: 0; }
.comparison-label { display: block; color: var(--text-sub); font-size: 20rpx; }
.comparison-value-row { display: flex; align-items: baseline; gap: 6rpx; margin-top: 7rpx; }
.comparison-value { color: var(--text); font-size: 38rpx; font-weight: 800; letter-spacing: -0.5rpx; font-variant-numeric: tabular-nums; }
.comparison-value.muted { color: var(--text-dim); }
.comparison-unit { color: var(--text-sub); font-size: 17rpx; }
.comparison-divider { width: 1rpx; background: var(--divider); }
.low-price .comparison-value { color: #168A5B; }
.high-price .comparison-value { color: #C9363E; }
.change { grid-column: 1 / -1; font-size: 23rpx; font-weight: 650; }
.up { color: var(--up); }
.down { color: var(--down); }
.neutral { color: var(--text-dim); }
.summary-stats { display: flex; padding-top: 24rpx; border-top: 1rpx solid var(--divider); }
.metric { flex: 1; }
.metric + .metric { padding-left: 20rpx; border-left: 1rpx solid var(--divider); }
.metric-value { display: block; color: var(--text); font-size: 29rpx; font-weight: 700; font-variant-numeric: tabular-nums; }
.metric-value.source-metric { color: var(--primary); font-size: 24rpx; }
.metric-label { display: block; color: var(--text-sub); font-size: 20rpx; margin-top: 6rpx; }
.source-context { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; margin: 18rpx 0; padding: 20rpx 24rpx; background: var(--primary-soft); border: 1rpx solid var(--card-border); border-radius: 14rpx; }
.source-context-main { min-width: 0; }
.source-context-name { display: block; color: var(--text); font-size: 24rpx; font-weight: 700; }
.source-context-copy { display: block; color: var(--text-sub); font-size: 19rpx; line-height: 1.45; margin-top: 4rpx; }
.source-context-state { flex-shrink: 0; color: var(--text-sub); font-size: 20rpx; font-weight: 650; }
.source-context-state.live { color: var(--up); }
.source-context-state.unavailable { color: var(--down); }
.chart-section { padding: 0 12rpx 10rpx; overflow: hidden; }
.range-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); margin: 0 6rpx 6rpx; border-bottom: 1rpx solid var(--divider); }
.range-item { position: relative; min-height: 68rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 19rpx; white-space: nowrap; }
.range-item::after { content: ''; position: absolute; left: 50%; bottom: -1rpx; width: 0; height: 4rpx; border-radius: 4rpx 4rpx 0 0; background: var(--primary); transform: translateX(-50%); transition: width 160ms ease; }
.range-item.active { color: var(--text); font-weight: 700; }
.range-item.active::after { width: 34rpx; }
.range-summary { display: flex; margin: 18rpx 0; }
.range-cell { flex: 1; }
.range-cell.center { text-align: center; }
.range-cell:last-child { text-align: right; }
.range-label { display: block; color: var(--text-sub); font-size: 20rpx; }
.range-value { display: block; color: var(--text); font-size: 26rpx; font-weight: 700; margin-top: 6rpx; font-variant-numeric: tabular-nums; }
.range-value.primary { color: var(--primary); }
.source-details { overflow: hidden; }
.source-row { display: flex; align-items: center; justify-content: space-between; padding: 24rpx 28rpx; }
.source-row + .source-row { border-top: 1rpx solid var(--divider); }
.source-name { color: var(--text); font-size: 26rpx; font-weight: 650; display: block; }
.source-meta { color: var(--text-dim); font-size: 19rpx; margin-top: 7rpx; display: block; }
.source-price { min-width: 230rpx; text-align: right; }
.source-band { display: flex; justify-content: flex-end; gap: 16rpx; font-size: 22rpx; font-weight: 700; font-variant-numeric: tabular-nums; }
.source-low { color: #168A5B; }
.source-high { color: #C9363E; }
.source-original { display: block; color: var(--text-sub); font-size: 19rpx; margin-top: 6rpx; }
.market-link { display: flex; justify-content: space-between; align-items: center; padding: 26rpx 28rpx; margin-top: 18rpx; }
.link-title { display: block; color: var(--text); font-size: 27rpx; font-weight: 650; }
.link-copy { display: block; color: var(--text-sub); font-size: 20rpx; margin-top: 6rpx; }
.link-arrow { color: var(--primary); font-size: 42rpx; }
.data-note { padding: 24rpx 28rpx; margin-top: 18rpx; }
.note-title { display: block; color: var(--text); font-size: 23rpx; font-weight: 650; }
.note-copy { display: block; color: var(--text-sub); font-size: 20rpx; line-height: 1.55; margin-top: 8rpx; }
.empty-state { padding: 80rpx 30rpx; text-align: center; }
.empty-title { display: block; color: var(--text); font-size: 27rpx; font-weight: 650; }
.empty-copy { display: block; color: var(--text-sub); font-size: 21rpx; margin-top: 10rpx; }
.market-skeleton { padding: 30rpx; }
.sk-line, .sk-chart { background: var(--divider); border-radius: 10rpx; }
.sk-line.wide { width: 42%; height: 24rpx; }
.sk-line.price { width: 58%; height: 58rpx; margin-top: 28rpx; }
.sk-chart { height: 250rpx; margin-top: 30rpx; }
.list-skeleton { margin-top: 16rpx; overflow: hidden; background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }
.list-skeleton-row { min-height: 132rpx; display: flex; align-items: center; gap: 20rpx; padding: 24rpx 28rpx; }
.list-skeleton-row + .list-skeleton-row { border-top: 1rpx solid var(--divider); }
.sk-rank, .sk-copy, .sk-value { background: var(--divider); border-radius: 9rpx; }
.sk-rank { width: 38rpx; height: 38rpx; }
.sk-copy { flex: 1; height: 54rpx; }
.sk-value { width: 120rpx; height: 48rpx; }
.retry-link { display: inline-flex; min-height: 64rpx; align-items: center; margin-top: 14rpx; color: var(--primary); font-size: 23rpx; font-weight: 700; }
.ranking-row, .region-row { display: flex; align-items: center; background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); padding: 26rpx 28rpx; margin-top: 14rpx; }
.rank { width: 52rpx; color: var(--text-dim); font-size: 30rpx; font-weight: 750; }
.rank-main { flex: 1; min-width: 0; }
.rank-name, .region-name { display: block; color: var(--text); font-size: 27rpx; font-weight: 650; }
.rank-meta, .region-meta { display: block; color: var(--text-sub); font-size: 20rpx; margin-top: 7rpx; }
.rank-price, .region-values { flex-shrink: 0; text-align: right; margin-left: 20rpx; }
.rank-label, .region-label { display: block; color: var(--text-sub); font-size: 18rpx; }
.rank-value, .region-price { display: block; color: var(--text); font-size: 27rpx; font-weight: 700; font-variant-numeric: tabular-nums; }
.rank-unit, .region-unit { display: block; color: var(--text-dim); font-size: 17rpx; margin-top: 3rpx; }
.rank-volatility { display: block; color: var(--primary); font-size: 20rpx; margin-top: 6rpx; font-variant-numeric: tabular-nums; }
.rank-range { display: block; color: var(--text-sub); font-size: 18rpx; line-height: 1.35; margin-top: 5rpx; font-variant-numeric: tabular-nums; }
.regional-model-scroll { margin-top: 20rpx; }
.regional-context { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; padding: 20rpx 2rpx 10rpx; }
.regional-context-title { display: block; color: var(--text); font-size: 27rpx; font-weight: 700; }
.regional-context-copy { display: block; margin-top: 5rpx; color: var(--text-sub); font-size: 19rpx; }
.regional-context-count { flex-shrink: 0; color: var(--primary); font-size: 20rpx; font-weight: 650; }
.regional-context-stats { flex-shrink: 0; text-align: right; }
.regional-context-status { display: block; color: var(--text-sub); font-size: 18rpx; margin-top: 5rpx; }
.regional-context-status.live { color: var(--up); }
.regional-context-status.delayed, .regional-context-status.stale { color: #b7791f; }
.regional-context-status.unavailable { color: var(--down); }
.region-row { align-items: flex-start; }
.region-row.cheapest { border-color: var(--primary); background: var(--primary-soft); }
.region-main { flex: 1; min-width: 0; }
.region-title-row { display: flex; align-items: center; gap: 10rpx; }
.lowest-badge { flex-shrink: 0; color: var(--primary); font-size: 18rpx; font-weight: 700; }
.region-range { display: block; color: var(--text-sub); font-size: 18rpx; margin-top: 7rpx; font-variant-numeric: tabular-nums; }
.region-spread { display: block; color: #C9363E; font-size: 19rpx; font-weight: 650; margin-top: 7rpx; font-variant-numeric: tabular-nums; }
.region-spread.baseline { color: var(--primary); }
.regional-note { margin-bottom: 12rpx; }
</style>
