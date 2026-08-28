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
const personalRebatePage = source('../src/pages/rebate/index.vue')
const supplierRebatePage = source('../src/pages/supplier/rebate.vue')
const supplierDashboard = source('../src/pages/supplier/dashboard.vue')
const profilePage = source('../src/pages/profile/index.vue')
const candleChart = source('../src/components/CandlestickChart.vue')
const marketChart = source('../src/components/MarketChart.vue')

test('KAI pricing remains available to market charts while product checkout is inquiry-only', () => {
  assert.match(gpuApi, /billing_unit\?: 'GPU_HOUR'/)
  assert.match(gpuApi, /price_cny_per_gpu_hour\?: number/)
  assert.match(gpuApi, /price_card_hours_per_gpu_hour\?: number/)
  assert.match(gpuApi, /wallet_charge_unit\?: 'CARD_HOUR'/)
  assert.match(productPage, /inquiryPriceHint/)
  assert.match(productPage, /saveInquiryRequestPrefill/)
  assert.doesNotMatch(productPage, /unitPriceCardHours|createOrder\(/)
  assert.match(marketPage, /modelPriceRangeText/)
  assert.match(marketPage, /submitRequirement/)
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

test('new inquiries retain bounded integer-hour requirements while legacy APIs remain readable', () => {
  assert.match(gpuApi, /purchase_unit\?: 'hour'/)
  assert.match(gpuApi, /purchase_hour_options\?: number\[\]/)
  assert.match(productPage, /DEFAULT_PURCHASE_HOURS = \[1, 6, 12, 24, 72, 168, 360, 720\]/)
  assert.match(productPage, /product\.value\?\.min_purchase_hours/)
  assert.match(productPage, /product\.value\?\.max_purchase_hours/)
  assert.match(productPage, /v-model\.number="hours"/)
  assert.match(productPage, /gpu_hours: hours\.value/)
  assert.match(productPage, /quantity: quantity\.value/)
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

test('hourly inquiry exposes usage requirements without creating a checkout', () => {
  assert.match(productPage, /t\('usageMode'\)/)
  assert.match(productPage, /saveInquiryRequestPrefill\(\{/)
  assert.match(productPage, /\/pages\/buy-request\/index\?compose=1/)
  assert.doesNotMatch(productPage, /createOrder\(|purchaseType|ensureRequestId/)
  assert.doesNotMatch(productPage, /t\('holdingMode'\)|confirmHoldingPurchase|buyHolding|purchaseType\s*=\s*'holding'/)
  const createBlock = orderApi.match(/export function createOrder[\s\S]*?\n\}/)?.[0] || ''
  assert.match(createBlock, /hours: number/)
  assert.match(createBlock, /purchase_type: PurchaseType/)
  assert.doesNotMatch(createBlock, /cycle_days/)
})

test('usage expiry rebate calculator remains valid but is not promised before inquiry confirmation', () => {
  const tiers = [
    { max_month_spent: 10000, rate: 3 },
    { max_month_spent: 50000, rate: 5 },
    { max_month_spent: 100000, rate: 7 },
    { max_month_spent: null, rate: 10 },
  ]
  assert.deepEqual(estimateUsageExpiryRebate(240, 'usage', true, 0, 10, tiers, 20000), { amount: 7.2, ratePercent: 3 })
  assert.deepEqual(estimateUsageExpiryRebate(20, 'usage', true, 9990, 10, tiers, 20000), { amount: 1, ratePercent: 5 })
  assert.deepEqual(estimateUsageExpiryRebate(720, 'usage', true, 50000, 10, tiers, 20000), { amount: 50.4, ratePercent: 7 })
  assert.deepEqual(estimateUsageExpiryRebate(720, 'usage', true, 100000, 10, tiers, 20000), { amount: 72, ratePercent: 10 })
  assert.deepEqual(estimateUsageExpiryRebate(1000, 'usage', true, 0, 10, tiers, 8), { amount: 8, ratePercent: 3 })
  assert.deepEqual(estimateUsageExpiryRebate(720, 'holding', true, 0, 10, tiers, 20000), { amount: 0, ratePercent: 0 })
  assert.deepEqual(estimateUsageExpiryRebate(720, 'usage', false, 0, 10, tiers, 20000), { amount: 0, ratePercent: 0 })
  assert.deepEqual(estimateUsageExpiryRebate(9.99, 'usage', true, 0, 10, tiers, 20000), { amount: 0, ratePercent: 0 })
  assert.deepEqual(estimateUsageExpiryRebate(33.5, 'usage', true, 0, 10, tiers, 20000), { amount: 1.01, ratePercent: 3 })
  assert.match(productPage, /inquiryPriceHint/)
  assert.doesNotMatch(productPage, /getRebateSummary|estimatedExpiryRebate|personalRebateEstimateHint|personalPurchaseRebateTier|estRebate/)
  assert.doesNotMatch(productPage, /USAGE_EXPIRY_REBATE_RATE_PERCENT/)
})

test('personal and merchant rebate policies stay separate in merchant mode', () => {
  assert.match(personalRebatePage, /personalRebateLockRule/)
  assert.match(personalRebatePage, /personalRebateExpiryRule/)
  assert.match(personalRebatePage, /info\.value\?\.tiers/)
  assert.match(personalRebatePage, /info\?\.monthly_cap/)
  assert.match(supplierRebatePage, /info\.value\?\.tiers/)
  assert.match(supplierRebatePage, /est_total_rebate/)
  assert.match(supplierRebatePage, /supplierRebateFormulaRule/)
  assert.match(supplierRebatePage, /info\?\.monthly_cap/)
  assert.doesNotMatch(`${personalRebatePage}\n${supplierRebatePage}`, /MONTHLY_REBATE_CAP_CARD_HOURS/)
  assert.doesNotMatch(supplierRebatePage, /service_fee_rate|服务费 =|返佣 = 服务费/)

  for (const merchantModePage of [profilePage, supplierDashboard]) {
    assert.match(merchantModePage, /getRebateSummary/)
    assert.match(merchantModePage, /getSupplierRebate/)
    assert.match(merchantModePage, /personalPurchaseRebate/)
    assert.match(merchantModePage, /merchantSalesRebate/)
  }
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

test('historical order views retain durations while renewal becomes a follow-up requirement', () => {
  for (const page of [orderList, orderDetail]) {
    assert.match(page, /duration_hours/)
    assert.match(page, /purchase_hours/)
    assert.match(page, /purchase_unit/)
    assert.match(page, /cycle_days/)
  }
  assert.match(orderList, /remaining_hours/)
  assert.match(orderDetail, /saveInquiryRequestPrefill\(\{/)
  assert.match(orderDetail, /submitFollowUpRequirement/)
  assert.match(orderDetail, /\/pages\/buy-request\/index\?compose=1/)
  assert.doesNotMatch(orderDetail, /renewOrder\(|pendingRenewRequestId|pendingRenewKey/)
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
