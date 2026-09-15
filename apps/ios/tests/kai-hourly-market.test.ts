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
const profilePage = source('../src/pages/profile/index.vue')
const personalRebatePage = source('../src/pages/rebate/index.vue')
const supplierRebatePage = source('../src/pages/supplier/rebate.vue')
const candleChart = source('../src/components/CandlestickChart.vue')
const marketChart = source('../src/components/MarketChart.vue')

test('KAI product contract distinguishes CNY pricing from wallet card-hours', () => {
  assert.match(gpuApi, /billing_unit\?: 'GPU_HOUR'/)
  assert.match(gpuApi, /price_cny_per_gpu_hour\?: number/)
  assert.match(gpuApi, /price_card_hours_per_gpu_hour\?: number/)
  assert.match(gpuApi, /wallet_charge_unit\?: 'CARD_HOUR'/)
  assert.match(productPage, /t\('inquiry'\)/)
  assert.match(productPage, /submitRequirement/)
  assert.doesNotMatch(productPage, /unitPriceCardHours|createOrder\(/)
  assert.match(marketPage, /t\('inquiry'\)/)
  assert.match(marketPage, /t\('submitRequirement'\)/)
  assert.doesNotMatch(marketPage, /productPriceCardHours|productPriceCny/)
})

test('home keeps representative KAI cards while market separates KAI and merchant catalogues', () => {
  assert.match(gpuApi, /representative\?: boolean/)
  assert.match(homePage, /page_size: 100, market_source: 'kai', representative: true/)
  assert.match(marketPage, /type MarketSourceFilter = 'kai' \| 'wod'/)
  assert.match(marketPage, /market_source: marketSource\.value/)
  assert.match(marketPage, /representative: marketSource\.value === 'kai'/)
  assert.match(marketPage, /merchantResourcesHint/)
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

test('new inquiry and renewal requests keep integer-hour requirements without checkout', () => {
  assert.match(gpuApi, /purchase_unit\?: 'hour'/)
  assert.match(gpuApi, /purchase_hour_options\?: number\[\]/)
  assert.match(productPage, /DEFAULT_PURCHASE_HOURS = \[1, 6, 12, 24, 72, 168, 360, 720\]/)
  assert.match(productPage, /product\.value\?\.min_purchase_hours/)
  assert.match(productPage, /product\.value\?\.max_purchase_hours/)
  assert.match(productPage, /v-model\.number="hours"/)
  assert.match(productPage, /saveInquiryRequestPrefill\([\s\S]*?gpu_hours: hours\.value/)
  assert.doesNotMatch(productPage, /createOrder\(/)
  assert.doesNotMatch(productPage, /purchaseCycles|cycleLabel/)
  assert.match(orderApi, /export type PurchaseType = 'usage'/)
  assert.match(orderApi, /expected_unit_price_card_hours\?: number/)
  assert.match(orderApi, /data: \{ product_id, hours, purchase_type, quantity, client_request_id, expected_unit_price_card_hours \}/)
  assert.match(orderApi, /renewOrder\(id: number, hours: number, client_request_id: string\)/)
  const createBlock = orderApi.match(/export function createOrder[\s\S]*?\n\}/)?.[0] || ''
  const renewBlock = orderApi.match(/export function renewOrder[\s\S]*?\n\}/)?.[0] || ''
  assert.doesNotMatch(createBlock, /cycle_days/)
  assert.match(renewBlock, /data: \{ hours, client_request_id \}/)
  assert.doesNotMatch(renewBlock, /product_id/)
})

test('hourly inquiry exposes usage requirements while retaining historical holding display elsewhere', () => {
  assert.match(productPage, /t\('hourlyComputeRequirement'\)/)
  assert.match(productPage, /saveInquiryRequestPrefill/)
  assert.match(productPage, /gpu_hours: hours\.value/)
  assert.doesNotMatch(productPage, /createOrder\(|walletBalance|confirmUsagePurchase/)
  assert.doesNotMatch(productPage, /t\('holdingMode'\)|confirmHoldingPurchase|buyHolding|purchaseType\s*=\s*'holding'/)
  const createBlock = orderApi.match(/export function createOrder[\s\S]*?\n\}/)?.[0] || ''
  assert.match(createBlock, /hours: number/)
  assert.match(createBlock, /purchase_type: PurchaseType/)
  assert.doesNotMatch(createBlock, /cycle_days/)
})

test('usage expiry rebate utility remains correct but is not advertised in inquiry checkout', () => {
  const tiers = [
    { max_month_spent: 10000, rate: 3 },
    { max_month_spent: 50000, rate: 5 },
    { max_month_spent: 100000, rate: 7 },
    { max_month_spent: null, rate: 10 },
  ]
  assert.deepEqual(estimateUsageExpiryRebate(240, 'usage', true, 0, 0, tiers, 20000), { amount: 7.2, ratePercent: 3 })
  assert.deepEqual(estimateUsageExpiryRebate(20, 'usage', true, 9990, 0, tiers, 20000), { amount: 1, ratePercent: 5 })
  assert.deepEqual(estimateUsageExpiryRebate(720, 'usage', true, 50000, 10, tiers, 20000), { amount: 50.4, ratePercent: 7 })
  assert.deepEqual(estimateUsageExpiryRebate(720, 'usage', true, 100000, 10, tiers, 20000), { amount: 72, ratePercent: 10 })
  assert.deepEqual(estimateUsageExpiryRebate(720, 'holding', true, 0, 0, tiers, 20000), { amount: 0, ratePercent: 0 })
  assert.deepEqual(estimateUsageExpiryRebate(720, 'usage', false, 0, 0, tiers, 20000), { amount: 0, ratePercent: 0 })
  assert.deepEqual(estimateUsageExpiryRebate(1000, 'usage', true, 100000, 0, tiers, 40), { amount: 40, ratePercent: 10 })
  assert.deepEqual(estimateUsageExpiryRebate(1000, 'usage', true, 0, 10, tiers, 8), { amount: 8, ratePercent: 3 })
  assert.deepEqual(estimateUsageExpiryRebate(9.99, 'usage', true, 0, 10, tiers, 20000), { amount: 0, ratePercent: 0 })
  assert.deepEqual(estimateUsageExpiryRebate(33.5, 'usage', true, 0, 10, tiers, 20000), { amount: 1.01, ratePercent: 3 })
  assert.deepEqual(estimateUsageExpiryRebate(10, 'usage', true, 0, 0, tiers, 0), { amount: 0, ratePercent: 0 })
  assert.doesNotMatch(productPage, /getRebateSummary|estimatedExpiryRebate|estRebate/)
  assert.doesNotMatch(productPage, /purchaseType === 'holding'/)
})

test('personal and seller rebate mechanisms are separate and explain their bases', () => {
  assert.match(profilePage, /supplierSalesRebateTitle/)
  assert.match(profilePage, /personalPurchaseRebateTitle/)
  assert.match(profilePage, /getSupplierRebate\(\), getRebateSummary\(\)/)
  assert.match(personalRebatePage, /personalPurchaseRebateRuleBasis/)
  assert.match(personalRebatePage, /info\.value\?\.tiers/)
  assert.match(personalRebatePage, /info\?\.monthly_cap \?\? 0/)
  assert.match(supplierRebatePage, /supplierSalesRebateRuleTarget/)
  assert.match(supplierRebatePage, /supplierSalesRebateRuleExclusions/)
  assert.match(supplierRebatePage, /info\.value\?\.tiers/)
  assert.match(supplierRebatePage, /info\?\.monthly_cap \?\? 0/)
  assert.doesNotMatch(`${personalRebatePage}\n${supplierRebatePage}`, /\?\? (?:20000|50000)/)
  assert.doesNotMatch(supplierRebatePage, /服务费 = 订单卡时|返佣 = 服务费/)
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
  assert.match(orderDetail, /submitRenewalRequirement/)
  assert.match(orderDetail, /saveInquiryRequestPrefill/)
  assert.doesNotMatch(orderDetail, /renewOrder\(|pendingRenewRequestId|续费成功/)
  assert.match(orderApi, /can_renew\?: boolean/)
  assert.match(orderDetail, /order\.value\?\.can_renew === true/)
  assert.match(orderDetail, /v-else-if="canRenew"/)
  assert.doesNotMatch(orderDetail, /order\.status === 'running' && isHourlyOrder/)
  assert.match(orderDetail, /order\.value\.can_cancel/)
  assert.match(orderDetail, /order\.value\.can_confirm/)
  assert.match(orderDetail, /order\.value\.can_dispute/)
  assert.match(orderDetail, /holdingSaleUnavailableNotice/)
  assert.doesNotMatch(orderDetail, /前往资产页可出售/)
})
