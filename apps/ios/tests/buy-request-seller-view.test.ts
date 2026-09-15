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

test('approved sellers can switch views and filter the request market to their quotes', () => {
  assert.match(page, /supplier_status === 'approved'/)
  assert.match(page, /viewTabs = computed\(\(\) => \[t\('availableRequests'\), t\('myBuyRequests'\)\]\)/)
  assert.match(page, /sellerScopeTabs = computed\(\(\) => \[t\('allRequests'\), t\('myQuotes'\)\]\)/)
  assert.match(page, /setSellerScopeTab/)
  assert.match(page, /requestedInitialView\.value === 'seller' && sellerViewAvailable\.value/)
  assert.match(page, /onLoad\(async \(options\) =>/)
  assert.match(page, /if \(requestedInitialView\.value === 'seller' && !composeRequested\.value\)/)
  assert.match(page, /requestedInitialSellerScope\.value = requestedInitialView\.value === 'seller' && String\(options\?\.scope \|\| ''\) === 'quoted' \? 'quoted' : 'all'/)
  assert.match(page, /getBuyRequests\(requestType\.value, 'seller', sellerScope\.value === 'quoted'\)/)
  assert.match(page, /getBuyRequests\(requestType\.value, 'buyer'\)/)
  assert.match(api, /export type BuyRequestView = 'buyer' \| 'seller'/)
  assert.match(api, /getBuyRequests\(requestType: 'online' \| 'offline', view: BuyRequestView = 'buyer', quotedOnly = false\)/)
  assert.match(api, /\.\.\.\(view === 'seller' && quotedOnly \? \{ quoted_only: true \} : \{\}\)/)
  assert.doesNotMatch(api, /quoted_only:\s*quotedOnly/)
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
  assert.match(page, /sellerScope\.value === 'quoted' \? 'noQuotedRequests' : 'noAvailableRequests'/)
  assert.match(page, /sellerScope\.value === 'quoted' \? 'sellerQuotedRequestHint' : 'sellerAvailableRequestHint'/)
  assert.doesNotMatch(page, /detail\.request\.(?:buyer_name|contact|phone)/)
  assert.match(page, /canBuyerSelectQuote/)
})

test('merchant operations expose a seller-default request market entry', () => {
  assert.match(widgets, /key: 'request-market'[\s\S]*?label: 'requestMarket'[\s\S]*?icon: 'procurement'[\s\S]*?route: '\/pages\/buy-request\/index\?view=seller'/)
  assert.match(i18n, /requestMarket: '需求市场'/)
  assert.match(i18n, /availableRequests: '可接需求'/)
  assert.match(i18n, /allRequests: '全部需求'/)
  assert.match(i18n, /myQuotes: '我的报价'/)
  assert.match(i18n, /noQuotedRequests: '暂无报价记录'/)
  assert.match(i18n, /sellerQuotedRequestHint: '你提交过报价的需求会显示在这里。'/)
  assert.match(i18n, /submitProposal: '提交方案报价'/)
  assert.match(i18n, /credentialEscrow: '凭证托管'/)
  assert.match(i18n, /requestMarket: 'Request Market'/)
  assert.match(i18n, /allRequests: 'All Requests'/)
  assert.match(i18n, /myQuotes: 'My Quotes'/)
  assert.match(i18n, /noQuotedRequests: 'No quotes yet'/)
  assert.match(i18n, /sellerQuotedRequestHint: 'Requests you have quoted on will appear here\.'/)
  assert.match(i18n, /lang\.value === 'zh-Hant' \? toTraditionalChinese\(value\) : value/)
})
