import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { estimateUsageExpiryRebate } from '../src/utils/product-rebate.ts'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const gpuApi = source('../src/api/gpu.ts')
const marketApi = source('../src/api/market.ts')
const orderApi = source('../src/api/order.ts')
const homePage = source('../src/pages/index/index.vue')
const productPage = source('../src/pages/product/detail.vue')
const quotePage = source('../src/pages/quote/index.vue')
const marketPage = source('../src/pages/market/index.vue')
const orderList = source('../src/pages/orders/index.vue')
const orderDetail = source('../src/pages/order/detail.vue')
const candleChart = source('../src/components/CandlestickChart.vue')
const marketChart = source('../src/components/MarketChart.vue')

test('KAI product contract distinguishes CNY pricing from wallet card-hours', () => {
  assert.match(gpuApi, /billing_unit\?: 'GPU_HOUR'/)
  assert.match(gpuApi, /price_cny_per_gpu_hour\?: number/)
  assert.match(gpuApi, /price_card_hours_per_gpu_hour\?: number/)
  assert.match(gpuApi, /wallet_charge_unit\?: 'CARD_HOUR'/)
  assert.match(productPage, /price_cny_per_gpu_hour \?\? product\.value\?\.price/)
  assert.match(productPage, /price_card_hours_per_gpu_hour \?\? toCardHours/)
  assert.match(productPage, /unitPriceCardHours\.value \* hours\.value \* quantity\.value/)
  assert.match(marketPage, /productPriceCardHours/)
  assert.match(marketPage, /cardHourPerGpuHour/)
  assert.match(marketPage, /productPriceCny/)
})

test('quote views render raw KAI CNY while shared charts keep explicit display units', () => {
  assert.match(quotePage, /display-currency="CNY"/)
  assert.match(quotePage, /cnyPricePerGpuHour/)
  assert.match(quotePage, /cnyPriceOrDash/)
  assert.match(quotePage, /t\('perGpuHour'\)/)
  assert.doesNotMatch(quotePage, /toCardHours|fmtCHn|cardHoursOrDash|cardHourNumber|cardHourPerGpuHour/)

  for (const chart of [candleChart, marketChart]) {
    assert.match(chart, /displayCurrency\?: 'CNY' \| 'CARD_HOUR'/)
    assert.match(chart, /displayCurrency: 'CARD_HOUR'/)
  }
  assert.match(candleChart, /props\.displayCurrency === 'CNY' \? Number\(value\) : toCardHours\(value\)/)
  assert.match(marketChart, /props\.displayCurrency === 'CNY' \? numericValue : toCardHours\(numericValue\)/)
  assert.match(candleChart, /props\.displayCurrency === 'CNY' \? `¥\$\{formatted\}` : formatted/)
  assert.match(marketChart, /props\.displayCurrency === 'CNY' \? `¥\$\{formatted\}` : formatted/)
})

test('new purchases and renewals are integer-hour only', () => {
  assert.match(gpuApi, /purchase_unit\?: 'hour'/)
  assert.match(gpuApi, /purchase_hour_options\?: number\[\]/)
  assert.match(productPage, /DEFAULT_PURCHASE_HOURS = \[1, 6, 12, 24, 72, 168, 720\]/)
  assert.match(productPage, /v-model\.number="hours"/)
  assert.match(productPage, /createOrder\(pid\.value, hours\.value, purchaseType\.value, quantity\.value/)
  assert.doesNotMatch(productPage, /purchaseCycles|cycleLabel/)
  assert.match(orderApi, /export type PurchaseType = 'usage' \| 'holding'/)
  assert.match(orderApi, /data: \{ product_id, hours, purchase_type, quantity, client_request_id \}/)
  assert.match(orderApi, /renewOrder\(id: number, hours: number, client_request_id: string\)/)
  const createBlock = orderApi.match(/export function createOrder[\s\S]*?\n\}/)?.[0] || ''
  const renewBlock = orderApi.match(/export function renewOrder[\s\S]*?\n\}/)?.[0] || ''
  assert.doesNotMatch(createBlock, /cycle_days/)
  assert.match(renewBlock, /data: \{ hours, client_request_id \}/)
  assert.doesNotMatch(renewBlock, /product_id/)
})

test('hourly checkout restores usage and holding without changing the duration contract', () => {
  assert.match(productPage, /const purchaseType = ref<'usage' \| 'holding'>\('usage'\)/)
  assert.match(productPage, /purchaseType === 'usage'/)
  assert.match(productPage, /purchaseType === 'holding'/)
  assert.match(productPage, /t\('usageMode'\)/)
  assert.match(productPage, /t\('holdingMode'\)/)
  assert.match(productPage, /purchaseType === 'usage' && rebate && estRebate > 0/)
  assert.match(productPage, /purchaseType === 'holding' \? 'confirmHoldingPurchase' : 'confirmUsagePurchase'/)
  assert.match(productPage, /`\$\{pid\.value\}:\$\{hours\.value\}:\$\{quantity\.value\}:\$\{purchaseType\.value\}`/)
  const createBlock = orderApi.match(/export function createOrder[\s\S]*?\n\}/)?.[0] || ''
  assert.match(createBlock, /hours: number/)
  assert.match(createBlock, /purchase_type: PurchaseType/)
  assert.doesNotMatch(createBlock, /cycle_days/)
})

test('usage expiry rebate follows the server policy and reacts to amount changes', () => {
  const tiers = [
    { max_month_spent: 10000, rate: 3 },
    { max_month_spent: 50000, rate: 5 },
    { max_month_spent: 100000, rate: 7 },
    { max_month_spent: null, rate: 10 },
  ]
  assert.deepEqual(estimateUsageExpiryRebate(240, 'usage', true, 0, 10, tiers), { amount: 7.2, ratePercent: 3 })
  assert.deepEqual(estimateUsageExpiryRebate(720, 'usage', true, 0, 10, tiers), { amount: 21.6, ratePercent: 3 })
  assert.deepEqual(estimateUsageExpiryRebate(720, 'holding', true, 0, 10, tiers), { amount: 0, ratePercent: 0 })
  assert.deepEqual(estimateUsageExpiryRebate(720, 'usage', false, 0, 10, tiers), { amount: 0, ratePercent: 0 })
  assert.deepEqual(estimateUsageExpiryRebate(20, 'usage', true, 9990, 10, tiers), { amount: 1, ratePercent: 5 })
  assert.deepEqual(estimateUsageExpiryRebate(9.99, 'usage', true, 0, 10, tiers), { amount: 0, ratePercent: 0 })
  assert.deepEqual(estimateUsageExpiryRebate(10, 'usage', true, 0, 10, tiers), { amount: 0.3, ratePercent: 3 })
  assert.deepEqual(estimateUsageExpiryRebate(33.5, 'usage', true, 0, 10, tiers), { amount: 1.01, ratePercent: 3 })
  assert.deepEqual(estimateUsageExpiryRebate(33.49, 'usage', true, 0, 10, tiers), { amount: 1, ratePercent: 3 })
  assert.match(productPage, /rebate\.value\?\.month_spent/)
  assert.match(productPage, /rebate\.value\?\.minimum_order_amount/)
  assert.match(productPage, /rebate\.value\?\.tiers/)
  assert.doesNotMatch(productPage, /total <= 10000|total <= 50000|total <= 100000/)
  assert.match(productPage, /estimatedExpiryRebate/)
  assert.match(productPage, /purchaseType === 'usage' && estRebate > 0/)
})

test('regional comparison is scoped to one model and VRAM identity', () => {
  assert.match(gpuApi, /getRegionalQuotes\(model: string, variant: string\)/)
  assert.match(gpuApi, /data: \{ model, variant \}/)
  assert.match(quotePage, /getRegionalQuotes\(model\.gpu_model, model\.gpu_variant \|\| ''\)/)
  assert.match(quotePage, /@tap="selectRegionalModel\(item\)"/)
  assert.match(quotePage, /sameModelRegionalComparison/)
  assert.match(quotePage, /quote_sample_count/)
  assert.match(quotePage, /location_count/)
  assert.match(quotePage, /median_price_cny/)
  assert.match(quotePage, /relative_to_lowest_pct/)
  assert.doesNotMatch(quotePage, /avg_price|resourceCount|sourceOptions/)
})

test('KAI quote observations are never typed or ranked as live inventory', () => {
  assert.match(marketApi, /available_gpu_count: number \| null/)
  assert.match(homePage, /quote_sample_count \?\? b\.sample_count/)
  assert.doesNotMatch(homePage, /b\.available_gpu_count - a\.available_gpu_count/)
  assert.doesNotMatch(quotePage, /b\.available_gpu_count - a\.available_gpu_count/)
})

test('new order views prefer hour duration while retaining legacy day fallback', () => {
  for (const page of [orderList, orderDetail]) {
    assert.match(page, /duration_hours/)
    assert.match(page, /purchase_hours/)
    assert.match(page, /purchase_unit/)
    assert.match(page, /cycle_days/)
  }
  assert.match(orderList, /remaining_hours/)
  assert.match(orderDetail, /renewOrder\(oid\.value, renewHours\.value, ensureRenewRequestId\(\)\)/)
  assert.match(orderDetail, /pendingRenewRequestId/)
  assert.match(orderDetail, /pendingRenewKey/)
  assert.match(orderDetail, /clearRenewRequest\(\)[\s\S]*?续费成功/)
  assert.match(orderDetail, /order\.value\.purchase_type === 'usage'/)
  assert.match(orderDetail, /\['running', 'completed'\]\.includes\(order\.value\.status\)/)
  assert.match(orderDetail, /v-else-if="canRenew"/)
  assert.doesNotMatch(orderDetail, /order\.status === 'running' && isHourlyOrder/)
  assert.match(orderDetail, /order\.value\?\.status !== 'paid'/)
  assert.match(orderDetail, /holdingSaleUnavailableNotice/)
  assert.doesNotMatch(orderDetail, /前往资产页可出售/)
})
