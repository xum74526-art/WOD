import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const api = source('../src/api/buy-request.ts')
const page = source('../src/pages/buy-request/index.vue')
const widgets = source('../src/config/profile-widgets.ts')
const i18n = source('../src/store/i18n.ts')

test('approved sellers can switch between available and personal request views', () => {
  assert.match(page, /supplier_status === 'approved'/)
  assert.match(page, /viewTabs = computed\(\(\) => \[t\('availableRequests'\), t\('myBuyRequests'\)\]\)/)
  assert.match(page, /requestedInitialView\.value === 'seller' && sellerViewAvailable\.value/)
  assert.match(page, /onLoad\(async \(options\) =>/)
  assert.match(page, /if \(requestedInitialView\.value === 'seller' && !composeRequested\.value\)/)
  assert.match(page, /getBuyRequests\(requestType\.value, 'seller'\)/)
  assert.match(page, /getBuyRequests\(requestType\.value, 'buyer'\)/)
  assert.match(api, /export type BuyRequestView = 'buyer' \| 'seller'/)
  assert.match(api, /data: \{ request_type: requestType, view \}/)
})

test('seller view keeps own requests protected and supports a complete proposal flow', () => {
  assert.match(page, /v-if="viewMode === 'buyer'" class="summary-strip"/)
  assert.match(page, /v-if="viewMode === 'buyer' && requests\.length" class="post-button"/)
  assert.match(page, /if \(viewMode\.value !== 'buyer' \|\| !commerce\.matchmakingEnabled\)/)
  assert.match(page, /typeof item\.is_own === 'boolean'/)
  assert.match(page, /Number\(item\.user_id\) === Number\(userStore\.userInfo\?\.id\)/)
  assert.match(page, /submitBuyRequestQuote/)
  assert.match(page, /counterBuyRequestQuote/)
  assert.match(page, /withdrawBuyRequestQuote/)
  assert.match(page, /MatchmakingQuoteForm/)
  assert.match(page, /buyerPrivacyProtected/)
  assert.match(page, /ownRequestReadOnlyHint/)
  assert.doesNotMatch(page, /detail\.request\.(?:buyer_name|contact|phone)/)
  assert.match(page, /canBuyerSelectQuote/)
})

test('merchant operations expose a seller-default request market entry', () => {
  assert.match(widgets, /key: 'request-market'[\s\S]*?label: 'requestMarket'[\s\S]*?icon: 'procurement'[\s\S]*?route: '\/pages\/buy-request\/index\?view=seller'/)
  assert.match(i18n, /requestMarket: '需求市场'/)
  assert.match(i18n, /availableRequests: '可接需求'/)
  assert.match(i18n, /submitProposal: '提交方案报价'/)
  assert.match(i18n, /credentialEscrow: '凭证托管'/)
  assert.match(i18n, /requestMarket: 'Request Market'/)
})
