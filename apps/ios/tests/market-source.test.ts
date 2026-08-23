import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const quoteSource = source('../src/pages/quote/index.vue')
const homeSource = source('../src/pages/index/index.vue')
const marketSource = source('../src/pages/market/index.vue')
const productSource = source('../src/pages/product/detail.vue')
const buyRequestSource = source('../src/pages/buy-request/index.vue')
const agreementSource = source('../src/pages/agreement/index.vue')
const gpuApiSource = source('../src/api/gpu.ts')
const orderApiSource = source('../src/api/order.ts')
const marketApiSource = source('../src/api/market.ts')
const chartSource = source('../src/components/MarketChart.vue')
const i18nSource = source('../src/store/i18n.ts')

test('current market requests are locked to KAI with no source selector', () => {
  assert.match(quoteSource, /selectedSources\s*=\s*ref<string\[\]>\(\['kai'\]\)/)
  assert.doesNotMatch(quoteSource, /const sourceOptions|toggleSource|key: 'autodl'|key: 'wod'/)
  assert.match(quoteSource, /class="source-context"/)
  assert.match(marketApiSource, /if \(!hasKai\) throw new Error\('KAI market source is required'\)/)
  assert.match(marketApiSource, /return \['kai'\]/)
})

test('retired sources never generate current market, catalog, detail, or buy-request calls', () => {
  assert.doesNotMatch(quoteSource, /\b(?:autodl|vast|wod_listing)\b/i)
  assert.match(quoteSource, /getLatestMarket\(model\.gpu_model, model\.gpu_variant, sources, silent\)/)
  assert.match(quoteSource, /getMarketCandles\(model\.gpu_model, model\.gpu_variant, range, sources/)
  assert.match(homeSource, /getProducts\(\{ page_size: 100, market_source: 'kai', representative: true \}\)/)
  assert.match(marketSource, /market_source: 'kai'/)
  assert.match(marketSource, /representative: true/)
  assert.match(productSource, /const candleRequest = source === 'kai'[\s\S]*?Promise\.resolve<MarketCandles \| null>\(null\)/)
  assert.match(productSource, /if \(source !== 'kai'\) return/)
  assert.match(buyRequestSource, /items\.filter\(\(item\) => item\.sources\.includes\('kai'\)\)/)
  assert.match(buyRequestSource, /getLatestMarket\(item\.gpu_model, item\.gpu_variant, \['kai'\], true\)/)
  assert.doesNotMatch(buyRequestSource, /autodl|sources\.push\('wod'\)/i)
  assert.doesNotMatch(source('../src/utils/home-market-policy.ts'), /sources:\s*\['(?:autodl|vast|wod)'\]/i)
})

test('current screens identify KAI while legacy detail labels use a neutral retired-source name', () => {
  assert.match(marketSource, /const name = t\('kaiPricingSource'\)/)
  assert.match(productSource, /marketSourceDisplayName\(product\.value\?\.market_source \|\| 'wod', t\)/)
  assert.match(quoteSource, /marketSourceDisplayName\(item\.source, t, item\.source_name\)/)
  assert.doesNotMatch([homeSource, marketSource, productSource, quoteSource, agreementSource, buyRequestSource].join('\n'), /AutoDL|Vast\.ai|WOD quotes|WOD 报价/i)
})

test('legacy protocol types remain readable while the agreement describes KAI-only hourly ordering', () => {
  assert.match(gpuApiSource, /market_source\?: 'wod' \| 'kai' \| 'vast' \| 'autodl'/)
  assert.match(gpuApiSource, /external_product_id\?: string \| null/)
  assert.match(orderApiSource, /market_source\?: 'wod' \| 'kai' \| 'vast' \| 'autodl'/)
  assert.match(chartSource, /kai:\s*\{\s*color:/)
  assert.match(chartSource, /vast:\s*\{\s*color:/)
  const kaiColor = chartSource.match(/kai:\s*\{\s*color:\s*'([^']+)'/)?.[1]
  const vastColor = chartSource.match(/vast:\s*\{\s*color:\s*'([^']+)'/)?.[1]
  assert.ok(kaiColor)
  assert.ok(vastColor)
  assert.notEqual(kaiColor, vastColor)
  assert.match(agreementSource, /当前仅接入 KAI 算力价格与可用报价/)
  assert.match(agreementSource, /Only current KAI pricing and available KAI offers are connected/)
  assert.match(agreementSource, /算力订单仅按整数小时购买/)
  assert.match(i18nSource, /kaiPricingSource: 'KAI 算力价格'/)
  assert.match(i18nSource, /kaiPricingSource: 'KAI Pricing'/)
  assert.match(i18nSource, /retiredMarketSourceUnavailableShort: '历史来源已停用'/)
  assert.match(i18nSource, /retiredMarketSourceUnavailableShort: 'Retired source'/)
})

test('KAI product detail scopes candles to its external product while aggregate charts stay unscoped', () => {
  assert.match(marketApiSource, /export interface MarketCandlesParams\s*\{[\s\S]*?external_product_id\?: string \| null[\s\S]*?\}/)
  assert.match(marketApiSource, /params: MarketCandlesParams = \{\}/)
  assert.match(marketApiSource, /encodeURIComponent\(externalProductId\)/)
  assert.match(marketApiSource, /externalProductId \? \{ external_product_id: externalProductId \} : \{\}/)

  assert.match(productSource, /if \(current\.market_source !== 'kai'\) return undefined/)
  assert.match(productSource, /current\.external_product_id/)
  assert.match(productSource, /productCandleParams\(product\.value\)/)
  assert.match(productSource, /productCandleParams\(current\)/)

  assert.doesNotMatch(homeSource, /external_product_id/)
  assert.doesNotMatch(quoteSource, /external_product_id/)
})
