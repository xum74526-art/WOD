import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const productDetail = source('../src/pages/product/detail.vue')
const buyRequest = source('../src/pages/buy-request/index.vue')
const login = source('../src/pages/login/index.vue')
const home = source('../src/pages/index/index.vue')
const market = source('../src/pages/market/index.vue')
const store = source('../src/pages/store/index.vue')
const gpuCard = source('../src/components/GPUCard.vue')
const wallet = source('../src/pages/wallet/index.vue')
const rechargeHistory = source('../src/pages/wallet/recharges.vue')
const orderDetail = source('../src/pages/order/detail.vue')
const assetDetail = source('../src/pages/asset/detail.vue')
const supplierRevenue = source('../src/pages/supplier/revenue.vue')

test('product inquiry saves context without creating or charging an order', () => {
  assert.match(productDetail, /saveInquiryRequestPrefill\(\{/)
  assert.match(productDetail, /\/pages\/buy-request\/index\?compose=1/)
  assert.match(productDetail, /submitRequirement/)
  assert.doesNotMatch(productDetail, /createOrder\(/)
  assert.doesNotMatch(productDetail, /fetchWallet|wallet\.value|amount\.value/)
})

test('request form is contact-first and contains product attribution without price limits', () => {
  assert.match(buyRequest, /readInquiryRequestPrefill\(\)/)
  assert.match(buyRequest, /product_id: inquiryContext\.value\?\.product_id/)
  assert.match(buyRequest, /supplier_id: inquiryContext\.value\?\.supplier_id/)
  assert.match(buyRequest, /source: inquiryContext\.value\?\.source/)
  assert.match(buyRequest, /product_name: inquiryContext\.value\?\.product_name/)
  assert.match(buyRequest, /!form\.contact\.trim\(\) \|\| !form\.phone\.trim\(\)/)
  assert.match(buyRequest, /clearInquiryRequestPrefill\(\)/)
  assert.doesNotMatch(buyRequest, /max_unit_price:|budget:/)
  assert.match(buyRequest, /selectBuyRequestQuote\(requestId, quoteId, expectedRevisionId\)/)
  assert.match(buyRequest, /canBuyerSelectQuote\(\{/)
  assert.match(buyRequest, /matchmakingEnabled: commerce\.matchmakingEnabled/)
  assert.match(buyRequest, /directTradeEnabled: commerce\.directTradeEnabled/)
  assert.match(buyRequest, /requestPlatformCoordinationHint/)
  assert.match(buyRequest, /counterBuyRequestQuote/)
})

test('login resumes the pending inquiry and public product cards use inquiry copy', () => {
  assert.match(login, /hasInquiryRequestPrefill\(\)/)
  assert.match(login, /reLaunch\(\{ url: '\/pages\/buy-request\/index\?compose=1' \}\)/)
  for (const page of [home, market, store, gpuCard]) {
    assert.match(page, /submitRequirement/)
    assert.doesNotMatch(page, /立即购买|Buy Now/)
  }
  assert.match(home, /\/pages\/buy-request\/index\?compose=1/)
  assert.match(home, /myBuyRequests/)
})

test('payment and historical lifecycle pages cannot start new money movement', () => {
  assert.doesNotMatch(wallet, /createRechargePayment|createWithdrawal|openRecharge|openWithdraw|continueCurrentPayment|requestReplaceRecharge|handleRestartRecharge/)
  assert.match(wallet, /queryRechargePayment/)
  assert.match(wallet, /cancelRechargePayment/)
  assert.doesNotMatch(rechargeHistory, /createRechargeRestartRoute|restartOrder|restartRecharge/)
  assert.match(rechargeHistory, /queryRechargePayment/)
  assert.match(rechargeHistory, /cancelRechargePayment/)
  assert.doesNotMatch(orderDetail, /renewOrder\(/)
  assert.doesNotMatch(assetDetail, /sellAsset\(/)
  assert.doesNotMatch(supplierRevenue, /@tap="onWithdraw"|function onWithdraw/)
})
