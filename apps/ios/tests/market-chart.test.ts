import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  candleChangePercent,
  formatSignedMarketPercent,
  formatSignedMarketPercentNumber,
} from '../src/utils/market-chart.ts'

const chartSource = readFileSync(new URL('../src/components/CandlestickChart.vue', import.meta.url), 'utf8')
const lineChartSource = readFileSync(new URL('../src/components/MarketChart.vue', import.meta.url), 'utf8')
const quoteSource = readFileSync(new URL('../src/pages/quote/index.vue', import.meta.url), 'utf8')

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

test('K-line change is always visible and unsupported 30-day range is hidden', () => {
  assert.match(chartSource, /class="readout-change"/)
  assert.match(chartSource, /candleChangeValue/)

  const rangesBlock = quoteSource.match(/const ranges = computed\(\(\) => \[([\s\S]*?)\n\]\)/)?.[1] || ''
  assert.ok(rangesBlock.includes("key: '7d'"))
  assert.ok(!rangesBlock.includes("key: '30d'"))
  assert.match(quoteSource, /candlePeriodChange\.value \?\?/)
})

test('candles and price lines render together without a mode switch', () => {
  assert.doesNotMatch(chartSource, /class="mode-switch"/)
  assert.doesNotMatch(chartSource, /class="mode-button"/)
  assert.doesNotMatch(chartSource, /const chartMode/)
  assert.match(chartSource, /candles\.map\(\(item, index\) => \{/)
  assert.match(chartSource, /linePath\(candles\.map\(\(item\) => item\.close\)/)
  assert.match(chartSource, /\$\{market\}\$\{priceTrend\}\$\{averages\}/)
  assert.match(chartSource, /t\('mergedMarketChart'\)/)
  assert.match(chartSource, /t\('priceTrendLine'\)/)
})

test('quote charts can display raw CNY without changing shared card-hour defaults', () => {
  assert.match(quoteSource, /display-currency="CNY"/)
  assert.doesNotMatch(quoteSource, /toCardHours|cardHoursOrDash|cardHourNumber/)

  for (const source of [chartSource, lineChartSource]) {
    assert.match(source, /displayCurrency\?: 'CNY' \| 'CARD_HOUR'/)
    assert.match(source, /displayCurrency: 'CARD_HOUR'/)
  }
  assert.match(chartSource, /function displayPrice\(value: number\)/)
  assert.match(chartSource, /props\.displayCurrency === 'CNY' \? Number\(value\) : toCardHours\(value\)/)
  assert.match(lineChartSource, /function displayPrice\(value: number \| null\)/)
  assert.match(lineChartSource, /props\.displayCurrency === 'CNY' \? numericValue : toCardHours\(numericValue\)/)
})

test('trend compares observed high and low while ranking and regions expose the real median', () => {
  assert.match(chartSource, /rising \? '#E5484D'/)
  assert.match(chartSource, /falling \? '#16A36A'/)
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
