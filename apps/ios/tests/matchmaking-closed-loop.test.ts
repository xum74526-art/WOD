import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  canBuyerConfirmDelivery,
  canBuyerReportDelivery,
  canBuyerSelectQuote,
  canBuyerViewCredential,
  canCounterQuote,
  canSellerSubmitQuote,
  canSupplierConfirmDeal,
  canSupplierSubmitCredential,
  canWithdrawQuote,
} from '../src/utils/matchmaking-actions.ts'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const quote = { id: 9, buy_request_id: 3, supplier_id: 5, supplier_name: 'Merchant', total_price: 240, currency: 'CNY', status: 'active' }

test('proposal actions are role and lifecycle gated', () => {
  assert.equal(canSellerSubmitQuote({ matchmakingEnabled: true, isOwnRequest: false, requestStatus: 'published' }), true)
  assert.equal(canSellerSubmitQuote({ matchmakingEnabled: true, isOwnRequest: true, requestStatus: 'published' }), false)
  assert.equal(canSellerSubmitQuote({ matchmakingEnabled: false, isOwnRequest: false, requestStatus: 'published' }), false)
  assert.equal(canCounterQuote({ matchmakingEnabled: true, role: 'buyer', isOwnRequest: true, requestStatus: 'quoting', quote }), true)
  assert.equal(canCounterQuote({ matchmakingEnabled: true, role: 'seller', isOwnRequest: false, requestStatus: 'quoting', quote }), true)
  assert.equal(canCounterQuote({ matchmakingEnabled: true, role: 'seller', isOwnRequest: false, requestStatus: 'quoting', quote: { ...quote, latest_revision: { total_price: 240, currency: 'CNY', actor_role: 'supplier' } } }), false)
  assert.equal(canWithdrawQuote({ matchmakingEnabled: true, isOwnRequest: false, requestStatus: 'active', quote }), true)
  assert.equal(canBuyerSelectQuote({ matchmakingEnabled: true, directTradeEnabled: false, isOwnRequest: true, requestStatus: 'active', quote }), true)
})

test('deal actions require both the expected status and an allowed capability flag', () => {
  const deal = { id: 7, status: 'buyer_selected', quote_id: 9, supplier_id: 5 }
  assert.equal(canSupplierConfirmDeal(deal), true)
  assert.equal(canSupplierConfirmDeal({ ...deal, can_supplier_confirm: false }), false)
  assert.equal(canSupplierSubmitCredential({ ...deal, status: 'credential_pending' }), true)
  assert.equal(canBuyerViewCredential({ ...deal, status: 'credential_released' }), true)
  assert.equal(canBuyerConfirmDelivery({ ...deal, status: 'credential_released' }), true)
  assert.equal(canBuyerReportDelivery({ ...deal, status: 'completed' }), false)
})

test('mobile API uses the canonical closed-loop endpoints', () => {
  const api = source('../src/api/buy-request.ts')
  assert.match(api, /`\/buy-requests\/\$\{requestId\}\/quotes`/)
  assert.match(api, /`\/buy-requests\/\$\{requestId\}\/quotes\/\$\{quoteId\}\/counter`/)
  assert.match(api, /`\/buy-requests\/\$\{requestId\}\/quotes\/\$\{quoteId\}\/withdraw`/)
  assert.match(api, /`\/buy-requests\/\$\{requestId\}\/deals\/\$\{dealId\}\/supplier-confirm`/)
  assert.match(api, /`\/buy-requests\/\$\{requestId\}\/deals\/\$\{dealId\}\/supplier-decline`/)
  assert.match(api, /`\/buy-requests\/\$\{requestId\}\/deals\/\$\{dealId\}\/credential`/)
  assert.match(api, /`\/buy-requests\/\$\{requestId\}\/deals\/\$\{dealId\}\/confirm-delivery`/)
  assert.match(api, /`\/buy-requests\/\$\{requestId\}\/deals\/\$\{dealId\}\/report-delivery`/)
})

test('matchmaking surfaces protect buyer contact and use non-financial coordination copy', () => {
  const page = source('../src/pages/buy-request/index.vue')
  const i18n = source('../src/store/i18n.ts')
  assert.doesNotMatch(page, /detail\.request\.(?:buyer_name|contact|phone)/)
  assert.match(page, /viewMode === 'seller' \? 'anonymousRequestId' : 'requestId'/)
  assert.match(i18n, /anonymousRequestId: '匿名需求 #\{id\}'/)
  assert.match(i18n, /requestId: '需求 #\{id\}'/)
  assert.match(i18n, /requestId: 'Request #\{id\}'/)
  assert.match(i18n, /platformCoordination: '平台协调'/)
  assert.match(i18n, /credentialEscrow: '凭证托管'/)
  assert.match(i18n, /submitProposal: '提交方案报价'/)
  const matchmakingCopy = [...i18n.matchAll(/(?:platformCoordination|credentialEscrow|submitProposal|buyerPrivacyProtectedHint|requestPlatformCoordinationHint): '([^']+)'/g)].map(match => match[1]).join(' ')
  assert.doesNotMatch(matchmakingCopy, /支付|付款|payment|paid/i)
})
