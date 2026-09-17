import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const gpuApi = source('../src/api/gpu.ts')
const homePage = source('../src/pages/index/index.vue')
const marketPage = source('../src/pages/market/index.vue')
const productPage = source('../src/pages/product/detail.vue')
const orderPage = source('../src/pages/order/detail.vue')
const i18n = source('../src/store/i18n.ts')
const agreementPage = [source('../src/pages/agreement/index.vue'), source('../src/config/legal-documents.ts')].join('\n')

test('frontend contract prefers neutral KAI manual-fulfillment semantics and reads legacy responses', () => {
  assert.match(gpuApi, /'platform_manual_fulfillment_allocation'/)
  assert.match(gpuApi, /'platform_closed_test_manual_fulfillment_allocation'/)
  assert.match(gpuApi, /stock_semantics\?: ProductStockSemantics \| null/)
})

test('KAI stock is never presented as live rentable inventory', () => {
  assert.match(marketPage, /isKaiProduct\(p\) \? 'kaiFulfillmentAllocation' : 'availableQuantity'/)
  assert.match(productPage, /isKaiProduct \? 'kaiFulfillmentAllocation' : 'k_40a4b798'/)
  assert.match(productPage, /inquiryFlowHint/)
  assert.match(productPage, /kaiProductDescription/)
  assert.doesNotMatch(homePage, /t\(['"]rentable['"]\)/)
})

test('KAI inquiry affordances retain allocation metadata without creating checkout', () => {
  assert.match(homePage, /t\('submitRequirement'\)/)
  assert.match(marketPage, /t\('submitRequirement'\)/)
  assert.match(gpuApi, /source_max_configurable_quantity\?: number \| null/)
  assert.match(productPage, /sourceOrderLimit = Math\.max/)
  assert.match(productPage, /Math\.min\(remaining, sourceOrderLimit\)/)
  assert.match(productPage, /const MAX_INQUIRY_QUANTITY = 99/)
  assert.match(productPage, /quantityLimit = computed\(\(\) => commerce\.directTradeEnabled \? Math\.max\(maxQuantity\.value, 1\) : MAX_INQUIRY_QUANTITY\)/)
  assert.match(productPage, /saveInquiryRequestPrefill/)
  assert.doesNotMatch(productPage, /createOrder\(/)
  assert.doesNotMatch(orderPage, /rentable|实时库存|live inventory/i)
})

test('KAI purchase wording is complete and positive in Chinese and English', () => {
  const retiredTestCopy = /封闭测试|闭测|功能测试|功能验证|历史测试|测试版|测试奖励|测试收益|测试卡片|测试交易|closed[- ]test|functional[- ]validation|historical test|test build|test reward|test return|test card|test transaction/i

  assert.match(i18n, /kaiFulfillmentAllocation: '可购数量'/)
  assert.match(i18n, /kaiAvailableAllocationHint: '当前可购 \{count\} 台'/)
  assert.match(i18n, /kaiFulfillmentAllocationNotice: '下单后，算力星图平台将为您协调交付有效 SSH。/)
  assert.match(i18n, /kaiProductDescription: 'KAI Pricing 当前 GPU 小时报价，支持按小时选择数量和使用时长。'/)
  assert.match(i18n, /kaiFulfillmentAllocation: 'Available quantity'/)
  assert.match(i18n, /kaiAvailableAllocationHint: 'Available now: \{count\} GPUs'/)
  assert.match(i18n, /kaiFulfillmentAllocationNotice: 'After ordering, 算力星图 coordinates valid SSH delivery for you\./)
  assert.match(i18n, /kaiProductDescription: 'Current KAI Pricing GPU-hour quote with hourly quantity and duration selection\.'/)
  assert.doesNotMatch(i18n, /不是 KAI 上游实时库存|not live upstream KAI inventory/i)
  assert.doesNotMatch(i18n, retiredTestCopy)
  assert.doesNotMatch(agreementPage, retiredTestCopy)
})
