import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const requests = source('../src/pages/buy-request/index.vue')
const wallet = source('../src/pages/wallet/index.vue')

test('buyer proposals expose currency-safe amounts but never buyer contact details', () => {
  assert.match(requests, /quoteAmount\(quote\)/)
  assert.match(requests, /latestQuoteRevision\(quote as BuyRequestQuote\)/)
  assert.match(requests, /formatQuoteAmount\(latest\.total_price, latest\.currency, t\('cardHour'\)\)/)
  assert.match(requests, /detail\.request\.gpu_hours/)
  assert.doesNotMatch(requests, /detail\.request\.(?:contact|phone|buyer_name)/)
})

test('matching request statuses use one submitted-discussion-confirmed lifecycle', () => {
  assert.match(requests, /active: 'statusPlanDiscussion'/)
  assert.match(requests, /processing: 'statusPlanDiscussion'/)
  assert.match(requests, /quote_selected: 'statusConfirmed'/)
  assert.match(requests, /coordination_requested: 'statusPlatformReview'/)
})

test('historical recharge queries depend on history capability and order capability only', () => {
  assert.match(wallet, /commerce\.historyReadEnabled && pendingPayment\.value && rechargeCanQuery/)
  assert.match(wallet, /queryProvider[\s\S]*?commerce\.historyReadEnabled[\s\S]*?payment\.can_query !== false/)
  assert.doesNotMatch(wallet, /rechargeEnabled\.value/)
})
