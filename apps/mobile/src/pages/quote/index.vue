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
                  <text v-if="latest?.summary.min_price_cny != null" class="comparison-value">{{ cardHourNumber(latest.summary.min_price_cny) }}</text>
                  <text v-else class="comparison-value muted">--</text>
                  <text class="comparison-unit">{{ t('cardHourPerGpuHour') }}</text>
                </view>
              </view>
              <view class="comparison-divider"></view>
              <view class="comparison-price high-price">
                <text class="comparison-label">{{ t('highestPrice') }}</text>
                <view class="comparison-value-row">
                  <text v-if="latest?.summary.max_price_cny != null" class="comparison-value">{{ cardHourNumber(latest.summary.max_price_cny) }}</text>
                  <text v-else class="comparison-value muted">--</text>
                  <text class="comparison-unit">{{ t('cardHourPerGpuHour') }}</text>
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
                <text class="metric-label">{{ t('validOffers') }}</text>
              </view>
              <view class="metric">
                <text class="metric-value">{{ latest?.summary.available_gpu_count || 0 }}</text>
                <text class="metric-label">{{ t('availableGpus') }}</text>
              </view>
              <view class="metric">
                <text class="metric-value">{{ latest?.summary.source_count || 0 }}</text>
                <text class="metric-label">{{ t('dataSources') }}</text>
              </view>
            </view>
          </view>

          <view class="source-switches">
            <view
              v-for="source in availableSourceOptions"
              :key="source.key"
              class="source-switch"
              :class="[{ active: selectedSources.includes(source.key) }, source.key]"
              @tap="toggleSource(source.key)"
            >
              <view class="line-swatch"></view>
              <text>{{ source.name }}</text>
            </view>
          </view>

          <view class="chart-section">
            <CandlestickChart
              :candles="displayedCandles"
              :source-note="historySourceText"
              :loading="refreshing && !candles"
              :error="candleLoadError && !candles"
              :history-state="chartHistoryState"
              :observed-days="chartObservedDays"
              :reference-price-cny="candles?.latest_live_price_cny ?? latest?.summary.median_price_cny"
              :reference-sample-count="latest?.summary.sample_count || 0"
              :reference-observed-at="candles?.latest_live_observed_at || latestObservedAt"
            />
            <view class="range-row">
              <view
                v-for="item in ranges"
                :key="item.key"
                class="range-item"
                :class="{ active: timeRange === item.key }"
                @tap="selectRange(item.key)"
              >{{ item.label }}</view>
            </view>
          </view>

          <view class="range-summary">
            <view class="range-cell">
              <text class="range-label">{{ t('lowestPrice') }}</text>
              <text class="range-value">{{ cardHoursOrDash(candleStats.low) }}</text>
            </view>
            <view class="range-cell center">
              <text class="range-label">{{ t('priceSpread') }}</text>
              <text class="range-value primary">{{ cardHoursOrDash(candleStats.spread) }}</text>
            </view>
            <view class="range-cell">
              <text class="range-label">{{ t('highestPrice') }}</text>
              <text class="range-value">{{ cardHoursOrDash(candleStats.high) }}</text>
            </view>
          </view>

          <view class="source-details">
            <view v-for="item in latest?.items || []" :key="item.source" class="source-row">
              <view class="source-main">
                <text class="source-name">{{ item.source_name }}</text>
                <text class="source-meta">{{ t('sampleCount', { count: item.sample_count }) }} · {{ sourceChecked(item) }}</text>
              </view>
              <view class="source-price">
                <view class="source-band">
                  <text class="source-low">{{ t('lowPriceShort') }} {{ cardHoursOrDash(item.min_price_cny) }}</text>
                  <text class="source-high">{{ t('highPriceShort') }} {{ cardHoursOrDash(item.max_price_cny) }}</text>
                </view>
                <text class="source-original">{{ originalPrice(item) }}</text>
              </view>
            </view>
          </view>

          <view class="market-link" @tap="goMarket">
            <view>
              <text class="link-title">{{ t('viewRentableResources') }}</text>
              <text class="link-copy">{{ t('marketMatchedResources', { count: latest?.summary.available_gpu_count || 0 }) }}</text>
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
        <view v-if="!ranking.length" class="empty-state"><text class="empty-title">{{ t('noVerifiedMarketData') }}</text></view>
        <view v-for="(item, index) in ranking" :key="`${item.gpu_model}-${item.gpu_variant}`" class="ranking-row" @tap="openTrend(item)">
          <text class="rank">{{ index + 1 }}</text>
          <view class="rank-main">
            <text class="rank-name">{{ item.gpu_model }} {{ item.gpu_variant }}</text>
            <text class="rank-meta">{{ t('sampleCount', { count: item.sample_count }) }} · {{ t('sourceCount', { count: item.source_count }) }}</text>
          </view>
          <view class="rank-price">
            <text class="rank-value">{{ cardHoursOrDash(item.median_price_cny) }}</text>
            <text class="rank-volatility" :class="changeTone(sevenDayChange(item))">{{ changeText(item) }}</text>
            <text class="rank-range">{{ priceRangeText(item) }}</text>
          <text v-if="item.change_24h != null" class="rank-change" :class="item.change_24h >= 0 ? 'up' : 'down'">{{ formatSignedMarketPercent(item.change_24h) }}</text>
            <text v-else class="rank-change neutral">--</text>
          </view>
        </view>
      </template>

      <template v-else>
        <view v-if="!regions.length" class="empty-state"><text class="empty-title">{{ t('noData') }}</text></view>
        <view v-for="item in regions" :key="item.region" class="region-row">
          <text class="region-name">{{ tr(item.region) }}</text>
          <view class="region-values">
            <text class="region-price">{{ t('averagePrice') }} {{ cardHours(item.avg_price) }}</text>
            <text class="region-meta">{{ t('lowestPrice') }} {{ cardHours(item.min_price) }} · {{ t('resourceCount', { count: item.count }) }}</text>
          </view>
        </view>
      </template>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { request } from '@/api/request'
import {
  getLatestMarket,
  getMarketCandles,
  getMarketModels,
  getMarketRanking,
  getMarketSourceStatus,
  type LatestMarket,
  type MarketCandles,
  type MarketModel,
  type MarketRankingItem,
  type MarketSnapshot,
  type MarketSourceState,
} from '@/api/market'
import AppNavBar from '@/components/AppNavBar.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import CandlestickChart from '@/components/CandlestickChart.vue'
import { useI18nStore } from '@/store/i18n'
import { fmtCH, fmtCHn, formatNumber, toCardHours } from '@/utils/format'
import { candleChangePercent, formatSignedMarketPercent, formatSignedMarketPercentNumber } from '@/utils/market-chart'
import {
  hasCompleteSevenDayMetric,
  trustedSevenDayChange,
  trustedSevenDayPriceRange,
} from '@/utils/market-list'
import {
  historyProvenanceLabel,
  marketHistoryDisplayState,
  marketObservedDayCount,
} from '@/utils/market-history'

const i18n = useI18nStore()
const { t, tr } = i18n
const tab = ref(0)
const models = ref<MarketModel[]>([])
const ranking = ref<MarketRankingItem[]>([])
const latest = ref<LatestMarket | null>(null)
const candles = ref<MarketCandles | null>(null)
const sourceStates = ref<MarketSourceState[]>([])
const regions = ref<any[]>([])
const selectedKey = ref('')
const selectedSources = ref<string[]>(['autodl', 'vast'])
const timeRange = ref('7d')
const refreshIn = ref(10)
const initialLoading = ref(true)
const refreshing = ref(false)
const candleLoadError = ref(false)
const requestedModel = ref('')
const requestedVariant = ref('')
let timer: ReturnType<typeof setInterval> | null = null
let refreshGeneration = 0
let candlesLoadedAt = 0
let candleRequestKey = ''
let sourceStatesLoadedAt = 0

const tabs = computed(() => [t('priceTrends'), t('modelRanking'), t('regionalPrices')])
const ranges = computed(() => [
  { key: '1h', label: t('oneHour') },
  { key: '6h', label: t('sixHours') },
  { key: '24h', label: t('twentyFourHours') },
  { key: '7d', label: t('sevenDays') },
])
const sourceOptions = computed(() => [
  { key: 'autodl', name: 'AutoDL' },
  { key: 'vast', name: 'Vast.ai' },
  { key: 'wod', name: '北斗 kai' },
])
const currentModel = computed(() => models.value.find((item) => modelKey(item) === selectedKey.value) || models.value[0])
const availableSourceOptions = computed(() => sourceOptions.value.filter((source) => currentModel.value?.sources.includes(source.key)))
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
const candlePeriodChange = computed(() => {
  const rows = displayedCandles.value
  if (rows.length < 2) return null
  return candleChangePercent(rows[0].open_price_cny, rows[rows.length - 1].close_price_cny)
})
const selectedSevenDayChange = computed(() => {
  if (chartHistoryState.value !== 'full') return null
  // Prefer the exact K-line series currently shown. Ranking data is only a
  // fallback because it may arrive later than the candle history request.
  return candlePeriodChange.value ?? (selectedMetric.value ? sevenDayChange(selectedMetric.value) : null)
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
function cardHourNumber(value: number) {
  return formatNumber(toCardHours(value))
}
function cardHours(value: number) { return fmtCH(value) }
function cardHoursOrDash(value?: number | null) { return value == null ? '--' : cardHours(value) }
function originalPrice(item: MarketSnapshot) {
  const suffix = item.currency === 'USD' && item.fx_date ? ` · ${item.fx_date}` : ''
  return `${formatNumber(item.min_price)}–${formatNumber(item.max_price)} ${item.currency}${suffix}`
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
  return [...items].sort((a, b) => {
    const av = hasCompleteSevenDayMetric(a) ? Math.abs(trustedSevenDayChange(a) || 0) : null
    const bv = hasCompleteSevenDayMetric(b) ? Math.abs(trustedSevenDayChange(b) || 0) : null
    if (av == null && bv == null) return b.sample_count - a.sample_count
    if (av == null) return 1
    if (bv == null) return -1
    return bv - av || b.sample_count - a.sample_count
  })
}

function prioritizeModels(items: MarketModel[]) {
  return [...items].sort((a, b) => {
    const aComplete = hasCompleteSevenDayMetric(a) ? 1 : 0
    const bComplete = hasCompleteSevenDayMetric(b) ? 1 : 0
    if (aComplete !== bComplete) return bComplete - aComplete
    const a4090 = a.gpu_model.replace(/\s+/g, '').toUpperCase() === 'RTX4090' ? 1 : 0
    const b4090 = b.gpu_model.replace(/\s+/g, '').toUpperCase() === 'RTX4090' ? 1 : 0
    if (a4090 !== b4090) return b4090 - a4090
    return b.available_gpu_count - a.available_gpu_count || b.sample_count - a.sample_count
  })
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
    ? t('sevenDayPriceRangeValue', { low: fmtCHn(range.low), high: fmtCHn(range.high) })
    : (Number(item.history_day_count || 0) > 1 ? t('chartObservedDays', { days: item.history_day_count }) : t('currentQuoteBaseline'))
}
function changeTone(value: number | null): string {
  return value == null || value === 0 ? 'neutral' : value > 0 ? 'rise' : 'fall'
}

async function loadBase() {
  initialLoading.value = true
  try {
    const [modelData, statusData] = await Promise.all([
      getMarketModels(),
      getMarketSourceStatus(),
    ])
    models.value = prioritizeModels(modelData.items)
    sourceStates.value = statusData.items
    sourceStatesLoadedAt = Date.now()
    if (!selectedKey.value && requestedModel.value) {
      const requested = models.value.find((item) => item.gpu_model === requestedModel.value && (!requestedVariant.value || item.gpu_variant === requestedVariant.value))
      if (requested) selectedKey.value = modelKey(requested)
    }
    if (!selectedKey.value && models.value.length) selectedKey.value = modelKey(models.value[0])
    if (currentModel.value) {
      selectedSources.value = selectedSources.value.filter((source) => currentModel.value!.sources.includes(source))
      if (!selectedSources.value.length) selectedSources.value = currentModel.value.sources.filter((source) => source !== 'wod').slice(0, 2)
      if (!selectedSources.value.length) selectedSources.value = currentModel.value.sources.slice(0, 2)
      await refreshPrices(false, true)
    }
    // Ranking includes the heavier seven-day comparison. It is useful for the
    // ranking tab, but must not block the current price and K-line card.
    void refreshRanking(true)
  } finally {
    initialLoading.value = false
  }
}

async function refreshRanking(silent = true) {
  try {
    ranking.value = prioritizeRanking((await getMarketRanking(silent)).items)
  } catch {
    // Keep the current price/K-line usable when ranking history is delayed.
  }
}

async function refreshPrices(silent = true, forceHistory = false) {
  if (!currentModel.value || !selectedSources.value.length) return
  const generation = ++refreshGeneration
  const model = currentModel.value
  const sources = [...selectedSources.value]
  const range = timeRange.value
  const billingMode = sources.every((source) => source === 'wod') ? 'wod_listing' : 'ondemand'
  // Current-price switches describe the live offer pool.  A seven-day chart
  // may additionally use the independently labelled Vast historical archive
  // when the selected live provider has only flat or incomplete observations.
  // The backend still selects one exact provider series and exposes its
  // provenance, so live and archive prices are never blended into one candle.
  const historySources = range === '7d' && !sources.includes('vast') && !sources.every((source) => source === 'wod')
    ? [...sources, 'vast']
    : sources
  const historyKey = `${model.gpu_model}|${model.gpu_variant}|${range}|${[...historySources].sort().join(',')}|${billingMode}`
  const historyRefreshMs = range === '7d' ? 5 * 60_000 : range === '24h' ? 30_000 : 8_000
  const needsHistory = forceHistory
    || !candles.value
    || candleRequestKey !== historyKey
    || Date.now() - candlesLoadedAt >= historyRefreshMs
  const needsSourceState = !sourceStates.value.length || Date.now() - sourceStatesLoadedAt >= 30_000
  refreshing.value = true
  try {
    const [latestResult, candleResult, stateResult] = await Promise.allSettled([
      getLatestMarket(model.gpu_model, model.gpu_variant, sources, silent),
      needsHistory
        ? getMarketCandles(model.gpu_model, model.gpu_variant, range, historySources, silent, billingMode)
        : Promise.resolve(candles.value),
      needsSourceState
        ? getMarketSourceStatus(silent)
        : Promise.resolve({ server_time: '', items: sourceStates.value }),
    ])
    // A model/source/range switch may happen while the previous request is in
    // flight. Only the latest selection is allowed to update the screen.
    if (generation !== refreshGeneration) return
    if (latestResult.status === 'rejected') throw latestResult.reason
    latest.value = latestResult.value
    if (candleResult.status === 'fulfilled' && candleResult.value) {
      candles.value = candleResult.value
      candleLoadError.value = false
      if (needsHistory) {
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
    refreshIn.value = latestResult.value.next_refresh_in || 10
  } catch {
    if (generation === refreshGeneration) refreshIn.value = 10
  } finally {
    if (generation === refreshGeneration) refreshing.value = false
  }
}

async function loadRegions() {
  try {
    const data = await request<{ regions: any[] }>({ url: '/products/quote/regional' })
    regions.value = data.regions
  } catch {}
}

function startTimer() {
  stopTimer()
  timer = setInterval(() => {
    if (typeof document !== 'undefined' && document.hidden) return
    refreshIn.value -= 1
    if (refreshIn.value <= 0) refreshPrices(true)
  }, 1000)
}
function stopTimer() { if (timer) { clearInterval(timer); timer = null } }
async function onTab(value: number) {
  tab.value = value
  if (value === 0 && !models.value.length) await loadBase()
  if (value === 1 && !ranking.value.length) await refreshRanking(false)
  if (value === 2 && !regions.value.length) await loadRegions()
}
async function selectModel(item: MarketModel) {
  selectedKey.value = modelKey(item)
  selectedSources.value = item.sources.filter((source) => source !== 'wod').slice(0, 2)
  if (!selectedSources.value.length) selectedSources.value = item.sources.slice(0, 2)
  latest.value = null
  candles.value = null
  candleLoadError.value = false
  await refreshPrices(false, true)
}
async function toggleSource(source: string) {
  if (selectedSources.value.includes(source)) {
    if (selectedSources.value.length === 1) return
    selectedSources.value = selectedSources.value.filter((item) => item !== source)
  } else {
    selectedSources.value = [...selectedSources.value, source]
  }
  await refreshPrices(false, true)
}
async function selectRange(value: string) { timeRange.value = value; await refreshPrices(false, true) }
function openTrend(item: MarketRankingItem) {
  const found = models.value.find((model) => model.gpu_model === item.gpu_model && model.gpu_variant === item.gpu_variant)
  if (found) selectModel(found)
  tab.value = 0
}
function goMarket() {
  if (currentModel.value) uni.setStorageSync('wod-market-keyword', currentModel.value.gpu_model)
  uni.switchTab({ url: '/pages/market/index' })
}

onLoad((options) => {
  requestedModel.value = options?.model ? decodeURIComponent(String(options.model)) : ''
  requestedVariant.value = options?.variant ? decodeURIComponent(String(options.variant)) : ''
})
onShow(async () => {
  i18n.updateTabBar()
  await loadBase()
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
.metric-label { display: block; color: var(--text-sub); font-size: 20rpx; margin-top: 6rpx; }
.source-switches { display: flex; gap: 12rpx; margin: 18rpx 0; }
.source-switch { flex: 1; display: flex; align-items: center; justify-content: center; gap: 10rpx; height: 62rpx; color: var(--text-sub); border: 1rpx solid var(--border); border-radius: 12rpx; font-size: 22rpx; background: var(--card); opacity: 0.58; }
.source-switch.active { opacity: 1; color: var(--text); }
.line-swatch { width: 12rpx; height: 12rpx; border-radius: 50%; background: var(--text-dim); }
.source-switch.active .line-swatch { background: var(--primary); }
.chart-section { padding: 14rpx 16rpx 10rpx; }
.range-row { display: flex; align-items: center; justify-content: space-between; padding: 10rpx 12rpx 4rpx; }
.range-item { color: var(--text-sub); font-size: 21rpx; padding: 10rpx 13rpx; border-radius: 10rpx; }
.range-item.active { color: var(--primary); background: var(--primary-soft); font-weight: 650; }
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
.ranking-row, .region-row { display: flex; align-items: center; background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); padding: 26rpx 28rpx; margin-top: 14rpx; }
.rank { width: 52rpx; color: var(--text-dim); font-size: 30rpx; font-weight: 750; }
.rank-main { flex: 1; min-width: 0; }
.rank-name, .region-name { display: block; color: var(--text); font-size: 27rpx; font-weight: 650; }
.rank-meta, .region-meta { display: block; color: var(--text-sub); font-size: 20rpx; margin-top: 7rpx; }
.rank-price, .region-values { text-align: right; }
.rank-value, .region-price { display: block; color: var(--text); font-size: 27rpx; font-weight: 700; font-variant-numeric: tabular-nums; }
.rank-volatility { display: block; color: var(--primary); font-size: 20rpx; margin-top: 6rpx; font-variant-numeric: tabular-nums; }
.rank-range { display: block; color: var(--text-sub); font-size: 18rpx; line-height: 1.35; margin-top: 5rpx; font-variant-numeric: tabular-nums; }
.rank-change { display: block; font-size: 20rpx; margin-top: 6rpx; }
.region-name { flex: 1; }
</style>
