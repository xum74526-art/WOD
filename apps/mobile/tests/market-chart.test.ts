import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  candleChangePercent,
  formatSignedMarketPercent,
  formatSignedMarketPercentNumber,
} from '../src/utils/market-chart.ts'

const chartSource = readFileSync(new URL('../src/components/CandlestickChart.vue', import.meta.url), 'utf8')
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

test('market view compares observed high and low without presenting a median', () => {
  assert.match(chartSource, /rising \? '#E5484D'/)
  assert.match(chartSource, /falling \? '#16A36A'/)
  assert.match(chartSource, /candles\.flatMap\(\(item\) => \[item\.low, item\.high\]\)/)
  assert.match(quoteSource, /latest\?\.summary\.min_price_cny/)
  assert.match(quoteSource, /latest\?\.summary\.max_price_cny/)
  assert.match(quoteSource, /t\('priceSpread'\)/)
  assert.doesNotMatch(quoteSource, /t\('medianPrice'\)/)
  assert.match(quoteSource, /class="source-low"/)
  assert.match(quoteSource, /class="source-high"/)
  assert.doesNotMatch(quoteSource, /class="source-cny"/)
})
