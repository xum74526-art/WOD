import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const product = source('../src/pages/product/detail.vue')
const requestPage = source('../src/pages/buy-request/index.vue')
const login = source('../src/pages/login/index.vue')
const home = source('../src/pages/index/index.vue')
const market = source('../src/pages/market/index.vue')
const store = source('../src/pages/store/index.vue')
const card = source('../src/components/GPUCard.vue')
const wallet = source('../src/pages/wallet/index.vue')
const rechargeHistory = source('../src/pages/wallet/recharges.vue')
const orderDetail = source('../src/pages/order/detail.vue')
const assetDetail = source('../src/pages/asset/detail.vue')
const supplierRevenue = source('../src/pages/supplier/revenue.vue')

test('product inquiry preserves configuration and market context without checkout', () => {
  assert.match(product, /CandlestickChart/)
  assert.match(product, /v-model\.number="hours"/)
  assert.match(product, /quantity\.value/)
  assert.match(product, /saveInquiryRequestPrefill\([\s\S]*?product_id:[\s\S]*?supplier_id:[\s\S]*?gpu_hours:/)
  assert.match(product, /\/pages\/buy-request\/index\?compose=1/)
  assert.doesNotMatch(product, /createOrder|getWallet|getRebateSummary|ConfirmSheet/)
})

test('request form requires contact details, carries listing identity, and supports closed-loop proposals', () => {
  assert.match(requestPage, /const contact = form\.contact\.trim\(\)/)
  assert.match(requestPage, /const phone = normalizeBuyRequestContactPhone\(form\.phone\)/)
  assert.match(requestPage, /product_id: inquiryContext\.value\?\.product_id/)
  assert.match(requestPage, /supplier_id: inquiryContext\.value\?\.supplier_id/)
  assert.match(requestPage, /source: inquiryContext\.value\?\.source/)
  assert.match(requestPage, /product_name: inquiryContext\.value\?\.product_name/)
  assert.match(requestPage, /clearInquiryRequestPrefill\(\)/)
  assert.match(requestPage, /String\(options\?\.compose \|\| ''\) === '1'/)
  assert.doesNotMatch(requestPage, /getLatestMarket|max_unit_price|budget:/)
  assert.match(requestPage, /selectBuyRequestQuote\(requestId, quoteId, expectedRevisionId\)/)
  assert.match(requestPage, /canBuyerSelectQuote\(\{/)
  assert.match(requestPage, /matchmakingEnabled: commerce\.matchmakingEnabled/)
  assert.match(requestPage, /directTradeEnabled: commerce\.directTradeEnabled/)
  assert.match(requestPage, /counterBuyRequestQuote/)
  assert.match(requestPage, /requestPlatformCoordinationHint/)
})

test('authentication and public catalogue entries return to the inquiry flow', () => {
  assert.match(login, /hasInquiryRequestPrefill\(\)/)
  assert.match(login, /reLaunch\(\{ url: '\/pages\/buy-request\/index\?compose=1' \}\)/)
  assert.match(home, /\/pages\/buy-request\/index\?compose=1/)
  assert.doesNotMatch(`${product}\n${login}\n${home}\n${orderDetail}\n${assetDetail}`, /\/pages\/buy-request\/index\?new=1/)
  for (const view of [home, market, store, card]) {
    assert.match(view, /inquiry/)
    assert.match(view, /submitRequirement/)
  }
})

test('financial history remains readable while new payment operations are absent', () => {
  assert.match(wallet, /queryRechargePayment/)
  assert.match(wallet, /cancelRechargePayment/)
  assert.match(rechargeHistory, /queryRechargePayment/)
  assert.match(rechargeHistory, /cancelRechargePayment/)
  assert.doesNotMatch(`${wallet}\n${rechargeHistory}`, /createRechargePayment|createWithdrawal|restartOrder|continueCurrentPayment/)
})

test('renewal uses inquiry while sell and supplier withdrawal writes stay unavailable', () => {
  assert.match(orderDetail, /submitRenewalRequirement/)
  assert.match(assetDetail, /submitRenewalRequirement/)
  assert.doesNotMatch(orderDetail, /renewOrder\(/)
  assert.doesNotMatch(assetDetail, /sellAsset\(/)
  assert.doesNotMatch(supplierRevenue, /onWithdraw|\/pages\/wallet\/index/)
})
