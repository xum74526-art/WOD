import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  candleChangePercent,
  formatSignedMarketPercent,
  formatSignedMarketPercentNumber,
} from '../src/utils/market-chart.ts'
import {
  candleBucketMilliseconds,
  candleBodyWidth,
  candleSlotCenter,
  candleTimeGeometry,
  canSharePriceDomain,
  chartLabelIndexes,
  chartPointerIndex,
  defaultCandleZoomLimit,
  movingAverage,
  nextCandleZoomLimit,
  paddedPriceDomain,
} from '../src/utils/candlestick-chart.ts'

const chartSource = readFileSync(new URL('../src/components/CandlestickChart.vue', import.meta.url), 'utf8')
const lineChartSource = readFileSync(new URL('../src/components/MarketChart.vue', import.meta.url), 'utf8')
const quoteSource = readFileSync(new URL('../src/pages/quote/index.vue', import.meta.url), 'utf8')
const homeSource = readFileSync(new URL('../src/pages/index/index.vue', import.meta.url), 'utf8')
const productSource = readFileSync(new URL('../src/pages/product/detail.vue', import.meta.url), 'utf8')
const marketApiSource = readFileSync(new URL('../src/api/market.ts', import.meta.url), 'utf8')

test('chart change displays zero only when observed open and close are equal', () => {
  assert.equal(candleChangePercent(2.4, 2.4), 0)
  assert.equal(formatSignedMarketPercent(candleChangePercent(2.4, 2.4)), '0%')

  const smallRise = candleChangePercent(2.4, 2.400000001)
  assert.ok(smallRise != null && smallRise > 0)
  assert.notEqual(formatSignedMarketPercent(smallRise), '0%')
  assert.match(formatSignedMarketPercent(smallRise), /^\+/)
  assert.notEqual(formatSignedMarketPercentNumber(smallRise), '0')
})

test('chart change preserves rise and fall directions', () => {
  assert.equal(formatSignedMarketPercent(candleChangePercent(2, 2.2)), '+10%')
  assert.equal(formatSignedMarketPercent(candleChangePercent(2, 1.8)), '-10%')
  assert.equal(candleChangePercent(0, 1), null)
})

test('K-line change is visible and only exposes ranges with complete official history', () => {
  assert.match(chartSource, /class="readout-change"/)
  assert.match(chartSource, /candleChangeValue/)

  const rangesBlock = quoteSource.match(/const ranges = computed[^\n]*\(\(\) => \[([\s\S]*?)\n\]\)/)?.[1] || ''
  assert.deepEqual(
    [...rangesBlock.matchAll(/key: '([^']+)'/g)].map((match) => match[1]),
    ['24h', '7d', '30d'],
  )
  assert.doesNotMatch(rangesBlock, /key: '(?:1h|3h|6h)'/)
  assert.match(rangesBlock, /key: '30d'[\s\S]*?t\('thirtyDays'\)/)
  assert.match(quoteSource, /\.range-row \{ display: grid; grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)/)
  assert.match(quoteSource, /\.range-item\.active::after \{ width: 34rpx; \}/)
  assert.match(quoteSource, /const timeRange = ref<MarketQuoteRange>\('30d'\)/)
  assert.match(marketApiSource, /export type MarketCandleRange = '1h' \| '3h' \| '6h' \| '24h' \| '7d' \| '30d'/)
  assert.match(marketApiSource, /export type MarketCandleApiRange = MarketCandleRange/)
  assert.match(marketApiSource, /export type MarketQuoteRange = Extract<MarketCandleApiRange, '24h' \| '7d' \| '30d'>/)
  assert.match(marketApiSource, /range: MarketCandleApiRange/)
  assert.match(quoteSource, /getMarketCandles\(model\.gpu_model, model\.gpu_variant, range,/)

  const sevenDayBlock = quoteSource.match(/const selectedSevenDayChange = computed\(\(\) => \{([\s\S]*?)\n\}\)/)?.[1] || ''
  assert.match(sevenDayBlock, /sevenDayChange\(selectedMetric\.value\)/)
  assert.doesNotMatch(sevenDayBlock, /candlePeriodChange|displayedCandles|timeRange/)
})

test('professional K-line prioritizes candles, current price and available averages', () => {
  assert.doesNotMatch(chartSource, /class="mode-switch"/)
  assert.match(chartSource, /candles\.map\(\(item, index\) => \{/)
  assert.doesNotMatch(chartSource, /const priceTrend/)
  assert.match(chartSource, /class="viewport-controls"/)
  assert.match(chartSource, /class="viewport-button"/)
  assert.match(chartSource, /props\.zoomable && !props\.compact/)
  assert.match(quoteSource, /<CandlestickChart[\s\S]*?zoomable/)
  assert.doesNotMatch(chartSource, /t\('mergedMarketChart'\)|t\('priceTrendLine'\)/)
  assert.match(chartSource, /t\('candlestickMode'\)/)
  assert.match(chartSource, /const latestPriceLine/)
  assert.match(chartSource, /const rawCloseTrend = \(props\.range === '1h' \|\| props\.range === '3h'\)/)
  assert.match(chartSource, /linePath\(candles\.map\(\(item\) => item\.close\), candles, x, y\)/)
  assert.match(chartSource, /candles\[index\]\.time - candles\[index - 1\]\.time > effectiveBucketMs \* 1\.5/)
  assert.match(chartSource, /const liveDisplayPrice/)
  assert.match(chartSource, /const baselineCanShareDomain/)
  assert.match(chartSource, /latestValue = baselineCanShareDomain\.value/)
  assert.match(chartSource, /!baselineCanShareDomain\.value \? \[\] : \[baselinePrice\.value\]/)
  assert.match(marketApiSource, /latest_live_comparable_to_history\?: boolean \| null/)
  for (const source of [quoteSource, homeSource, productSource]) {
    assert.match(source, /reference-comparable-to-history/)
    assert.match(source, /latest_live_comparable_to_history === true/)
    assert.doesNotMatch(source, /latest_live_comparable_to_history !== false/)
  }
  assert.match(chartSource, /const extremeMarks/)
  assert.match(chartSource, /preserveAspectRatio="xMidYMid meet"/)
  assert.match(chartSource, /maReadout\.length/)
  assert.match(chartSource, /value == null \? null/)
  assert.ok(quoteSource.indexOf('class="range-row"') < quoteSource.indexOf('<CandlestickChart'))
  assert.match(homeSource, /<CandlestickChart[\s\S]*?\n\s+compact/)
  assert.match(homeSource, /getMarketCandles\([\s\S]*?'30d'/)
  assert.match(homeSource, /t\('thirtyDays'\)[\s\S]*?t\('candlestickMode'\)/)
  assert.match(productSource, /getMarketCandles\([\s\S]*?'30d'/)
})

test('all K-line callers pass the selected range and backend bucket size to the chart', () => {
  assert.match(chartSource, /bucketSeconds\?: number/)
  assert.match(chartSource, /range\?: MarketCandleRange/)
  assert.match(chartSource, /props\.bucketSeconds/)
  assert.match(chartSource, /props\.range/)

  assert.match(quoteSource, /:bucket-seconds="candles\?\.bucket_seconds \|\| 0"/)
  assert.match(quoteSource, /:range="timeRange"/)
  assert.match(homeSource, /:bucket-seconds="activeHotTrend\.candles\?\.bucket_seconds \|\| 0"/)
  assert.match(homeSource, /range="30d"/)
  assert.match(productSource, /:bucket-seconds="candles\?\.bucket_seconds \|\| 0"/)
  assert.match(productSource, /range="30d"/)
})

test('K-line geometry keeps candles in slots and pointer selection out of the price axis', () => {
  assert.equal(candleSlotCenter(0, 3, 4, 309), 55.5)
  assert.equal(candleSlotCenter(2, 3, 4, 309), 261.5)
  assert.equal(candleBodyWidth(3, 309), 9)
  assert.ok(candleBodyWidth(60, 309) >= 2.6)
  assert.ok(candleBodyWidth(60, 309) <= 9)
  assert.deepEqual(chartLabelIndexes(30, 5), [0, 7, 15, 22, 29])
  assert.match(chartSource, /props\.compact[\s\S]*?\? 30[\s\S]*?requestedVisibleCount\.value : 60/)
  assert.match(chartSource, /props\.compact \|\| candles\.length < 20 \? 3 : 5/)

  assert.equal(chartPointerIndex(10, 0, 360, 7, 360, 4, 309), 0)
  assert.equal(chartPointerIndex(355, 0, 360, 7, 360, 4, 309), null)
  assert.equal(chartPointerIndex(158.5, 0, 360, 7, 360, 4, 309), 3)

  const geometry = candleTimeGeometry([0, 3_600_000, 10_800_000], 4, 309, 3_600)
  assert.equal(geometry.equivalentSlotCount, 4)
  assert.ok(geometry.centers[2] - geometry.centers[1] > geometry.centers[1] - geometry.centers[0])
  assert.equal(chartPointerIndex(geometry.centers[2], 0, 360, 3, 360, 4, 309, geometry.centers), 2)

  const inferredGeometry = candleTimeGeometry([0, 3_600_000, 10_800_000], 4, 309)
  assert.equal(inferredGeometry.equivalentSlotCount, 3)
  assert.equal(candleBucketMilliseconds([0, 3_600_000, 10_800_000]), 5_400_000)
})

test('K-line zoom uses bounded steps and always keeps the latest real candles', () => {
  assert.equal(defaultCandleZoomLimit('24h'), 36)
  assert.equal(defaultCandleZoomLimit('7d'), 42)
  assert.equal(defaultCandleZoomLimit('30d'), 45)
  assert.equal(defaultCandleZoomLimit('30d', true), 30)

  assert.equal(nextCandleZoomLimit('24h', 24, 24, 'in'), 18)
  assert.equal(nextCandleZoomLimit('24h', 18, 24, 'out'), 24)
  assert.equal(nextCandleZoomLimit('7d', 42, 42, 'in'), 28)
  assert.equal(nextCandleZoomLimit('30d', 30, 30, 'in'), 20)
  assert.equal(nextCandleZoomLimit('30d', 20, 30, 'out'), 30)
  assert.equal(nextCandleZoomLimit('30d', 7, 7, 'in'), 7)
  assert.equal(nextCandleZoomLimit('30d', 7, 7, 'out'), 7)
  assert.equal(nextCandleZoomLimit('30d', 60, 100, 'out'), 60)

  const rows = Array.from({ length: 100 }, (_, index) => index + 1)
  assert.deepEqual(rows.slice(-18), Array.from({ length: 18 }, (_, index) => index + 83))
  assert.equal(rows.slice(-18).at(-1), 100)
  assert.match(chartSource, /normalizedCandles\.value\.slice\(visibleStartIndex\.value\)/)
  assert.match(chartSource, /selectedRelativeIndex\.value = Math\.max\(0, Math\.min\(next, normalizedCandles\.value\.length\) - 1\)/)
  assert.match(quoteSource, /:key="selectedKey \+ ':' \+ timeRange"/)
})

test('moving averages and flat price domains remain numerically stable', () => {
  assert.deepEqual(movingAverage([1, 2, 3, 4, 5, 6], 5), [null, null, null, null, 3, 4])
  assert.deepEqual(movingAverage([1, 2], 0), [null, null])

  const domain = paddedPriceDomain([27, 27, 27])
  assert.ok(domain.min < 27)
  assert.ok(domain.max > 27)
  assert.ok(Number.isFinite(domain.min) && Number.isFinite(domain.max))

  const narrowDomain = paddedPriceDomain([5.0301, 5.03085])
  assert.ok(narrowDomain.max - narrowDomain.min < 0.002)

  assert.equal(canSharePriceDomain(26.96, [26.73, 27.05]), false)
  assert.equal(canSharePriceDomain(24.76, [26.73, 27.05], true), true)
  assert.equal(canSharePriceDomain(26.96, [26.73, 27.05], false), false)
})

test('quote charts convert canonical CNY into the selected language currency', () => {
  assert.doesNotMatch(quoteSource, /display-currency=/)
  assert.doesNotMatch(quoteSource, /toCardHours|cardHoursOrDash|cardHourNumber/)

  for (const source of [chartSource, lineChartSource]) {
    assert.doesNotMatch(source, /displayCurrency\?: 'CNY' \| 'CARD_HOUR'/)
    assert.match(source, /cnyToDisplayCurrency/)
    assert.match(source, /displayCurrencySymbol/)
  }
  assert.match(chartSource, /function displayPrice\(value: number\)/)
  assert.match(chartSource, /return cnyToDisplayCurrency\(value\)/)
  assert.match(lineChartSource, /function displayPrice\(value: number \| null\)/)
  assert.match(lineChartSource, /return cnyToDisplayCurrency\(numericValue\)/)
})

test('trend compares observed high and low while ranking and regions expose the real median', () => {
  assert.match(chartSource, /rising \? '#E4474F'/)
  assert.match(chartSource, /falling \? '#159B68'/)
  assert.match(chartSource, /candles\.flatMap\(\(item\) => \[item\.low, item\.high\]\)/)
  assert.match(quoteSource, /latest\?\.summary\.min_price_cny/)
  assert.match(quoteSource, /latest\?\.summary\.max_price_cny/)
  assert.match(quoteSource, /t\('priceSpread'\)/)
  assert.match(quoteSource, /t\('medianPrice'\)/)
  assert.match(quoteSource, /sameModelRegionalComparison/)
  assert.match(quoteSource, /quote_sample_count/)
  assert.match(quoteSource, /class="source-low"/)
  assert.match(quoteSource, /class="source-high"/)
  assert.doesNotMatch(quoteSource, /class="source-cny"/)
})
