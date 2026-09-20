import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { rechargeCanRequestRefund, rechargeRefundRequestPresentation } from '../src/utils/recharge-payment.ts'

const api = readFileSync(new URL('../src/api/wallet.ts', import.meta.url), 'utf8')
const page = readFileSync(new URL('../src/pages/wallet/recharges.vue', import.meta.url), 'utf8')

test('mobile exposes refund requests only for eligible Qixiang recharge states', () => {
  assert.equal(rechargeCanRequestRefund({ provider: 'qixiangpay', status: 'paid', credited_at: '2026-09-20T00:00:00' }), true)
  assert.equal(rechargeCanRequestRefund({ provider: 'qixiangpay', status: 'review' }), true)
  assert.equal(rechargeCanRequestRefund({ provider: 'qixiangpay', status: 'paid' }), false)
  assert.equal(rechargeCanRequestRefund({ provider: 'mapay', status: 'paid', credited_at: '2026-09-20T00:00:00' }), false)
  assert.equal(rechargeCanRequestRefund({ provider: 'qixiangpay', status: 'refunded', credited_at: '2026-09-20T00:00:00' }), false)
})

test('mobile refund status presentation separates pending and final outcomes', () => {
  assert.deepEqual(rechargeRefundRequestPresentation({ status: 'pending_review' }), { labelKey: 'refundRequestPendingReview', tone: 'pending' })
  assert.deepEqual(rechargeRefundRequestPresentation({ status: 'processing' }), { labelKey: 'refundRequestProcessing', tone: 'reviewing' })
  assert.deepEqual(rechargeRefundRequestPresentation({ status: 'succeeded' }), { labelKey: 'refundRequestSucceeded', tone: 'success' })
  assert.deepEqual(rechargeRefundRequestPresentation({ status: 'failed' }), { labelKey: 'refundRequestFailed', tone: 'danger' })
})

test('mobile keeps refund submission idempotent and exposes the request history', () => {
  assert.match(api, /\/refund-requests`/)
  assert.match(api, /retryUncertainOnce: true/)
  assert.match(page, /ensureClientRequestIntent\(/)
  assert.match(page, /createRechargeRefundRequest\(order\.order_no/)
  assert.match(page, /getRechargeRefundRequests\(/)
  assert.match(page, /refundApplications/)
  assert.match(page, /refundReviewNotice/)
})
