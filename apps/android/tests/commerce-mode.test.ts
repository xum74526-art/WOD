import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { parseDirectTradeBuildGate, resolveDirectTradeEnabled } from '../src/utils/commerce-mode.ts'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

test('review builds fail closed and a remote flag cannot enable direct trade', () => {
  assert.equal(parseDirectTradeBuildGate(undefined), false)
  assert.equal(parseDirectTradeBuildGate('false'), false)
  assert.equal(resolveDirectTradeEnabled(false, { direct_trade_enabled: true }), false)
  assert.match(source('../.env.example'), /VITE_ENABLE_DIRECT_TRADE=false/)
})

test('future direct builds retain a separately gated transaction branch', () => {
  assert.equal(parseDirectTradeBuildGate('TRUE'), true)
  assert.equal(resolveDirectTradeEnabled(true, { direct_trade_enabled: true }), true)
  assert.equal(resolveDirectTradeEnabled(true, { direct_trade_enabled: false }), false)
  assert.match(source('../src/components/direct-trade/DirectTradeProductCheckout.vue'), /createOrder/)
  assert.match(source('../src/components/direct-trade/DirectTradeWalletActions.vue'), /createRechargePayment/)
})

test('runtime matchmaking is explicit and capability failures remain closed', () => {
  const api = source('../src/api/platform.ts')
  const store = source('../src/store/commerce.ts')
  assert.match(api, /url: '\/platform\/capabilities'/)
  assert.match(store, /matchmaking_enabled === true/)
  assert.match(store, /direct_trade_enabled === true/)
  assert.match(store, /catch\(\(reason: unknown\) => failClosed/)
})
