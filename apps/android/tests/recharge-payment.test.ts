import test from 'node:test'
import assert from 'node:assert/strict'

import {
  formatPaymentCountdown,
  parseBackendTimestamp,
  paymentRemainingMs,
  readStoredRechargeSession,
  rechargeCanCancel,
  rechargeCanQuery,
  rechargeCanRestart,
  rechargeClearsCurrentSession,
  rechargeUiState,
} from '../src/utils/recharge-payment.ts'

test('naive backend timestamps are interpreted as UTC', () => {
  assert.equal(
    parseBackendTimestamp('2026-08-20T02:00:00'),
    Date.parse('2026-08-20T02:00:00Z'),
  )
})

test('server time drives the countdown even when client clock is wrong', () => {
  assert.equal(paymentRemainingMs({
    expires_at: '2026-08-20T02:05:00',
    server_time: '2026-08-20T02:01:30',
  }, Date.parse('2036-01-01T00:00:00Z')), 210_000)
  assert.equal(formatPaymentCountdown(210_000), '03:30')
})

test('remaining_seconds has priority over timestamps', () => {
  assert.equal(paymentRemainingMs({
    remaining_seconds: 42,
    expires_at: '2020-01-01T00:00:00Z',
  }), 42_000)
  assert.equal(paymentRemainingMs({
    remaining_seconds: null,
    expires_at: '2026-08-20T02:05:00Z',
    server_time: '2026-08-20T02:04:00Z',
  }), 60_000)
})

test('pending order becomes locally expired at zero but paid order is processing', () => {
  assert.equal(rechargeUiState({ status: 'pending' }, 0), 'expired')
  assert.equal(rechargeUiState({ status: 'paid' }, 0), 'processing')
  assert.equal(rechargeUiState({ status: 'review' }, 0), 'processing')
  assert.equal(rechargeUiState({ status: 'paid', credited_at: '2026-08-20T02:03:00Z' }, 0), 'success')
  assert.equal(rechargeUiState({ status: 'canceled' }, 0), 'canceled')
  assert.equal(rechargeUiState({ status: 'cancelled' }, 0), 'canceled')
})

test('recharge actions follow server state and never allow paid cancellation', () => {
  assert.equal(rechargeCanCancel({ status: 'pending', can_cancel: true }), true)
  assert.equal(rechargeCanCancel({ status: 'pending', can_cancel: false }), false)
  assert.equal(rechargeCanCancel({ status: 'paid', can_cancel: true }), false)
  assert.equal(rechargeCanCancel({ status: 'review', can_cancel: true }), false)
  assert.equal(rechargeCanCancel({ status: 'pending', credited_at: '2026-08-20T02:03:00Z', can_cancel: true }), false)
  assert.equal(rechargeCanQuery({ status: 'pending', can_query: true }), true)
  assert.equal(rechargeCanQuery({ status: 'pending', can_query: false }), false)
  assert.equal(rechargeCanRestart({ status: 'pending' }, 10_000), false)
  assert.equal(rechargeCanRestart({ status: 'expired' }, 0), true)
  assert.equal(rechargeCanRestart({ status: 'canceled' }, null), true)
})

test('a server-confirmed cancellation leaves history but clears the current checkout session', () => {
  assert.equal(rechargeClearsCurrentSession({ status: 'canceled' }), true)
  assert.equal(rechargeClearsCurrentSession({ status: 'cancelled' }), true)
  assert.equal(rechargeClearsCurrentSession({ status: 'expired' }), false)
  assert.equal(rechargeClearsCurrentSession({ status: 'paid' }), false)
})

test('legacy stored order number is upgraded without losing recovery', () => {
  assert.deepEqual(readStoredRechargeSession('WODR123'), {
    version: 1,
    orderNo: 'WODR123',
    checkoutUrl: '',
    fallbackExpiresAtMs: null,
    successNotified: false,
  })
  assert.deepEqual(readStoredRechargeSession({ version: 1, orderNo: 'WODR456' }), {
    version: 1,
    orderNo: 'WODR456',
    checkoutUrl: '',
    fallbackExpiresAtMs: null,
    successNotified: false,
  })
})
