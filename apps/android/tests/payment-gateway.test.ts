import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const walletApi = readFileSync(new URL('../src/api/wallet.ts', import.meta.url), 'utf8')
const walletPage = readFileSync(new URL('../src/pages/wallet/index.vue', import.meta.url), 'utf8')
const rechargeOrdersPage = readFileSync(new URL('../src/pages/wallet/recharges.vue', import.meta.url), 'utf8')
const locale = readFileSync(new URL('../src/store/i18n.ts', import.meta.url), 'utf8')

test('recharge transport uses only the Qixiang Pay API paths', () => {
  assert.match(walletApi, /provider: 'qixiangpay'/)
  assert.match(walletApi, /\/payments\/qixiang\/recharge-orders/)
  assert.match(walletApi, /\/payments\/qixiang\/orders/)
  assert.doesNotMatch(walletApi, /\/payments\/mapay\//)
})

test('recharge history supports server-authorized query and cancellation', () => {
  assert.match(walletApi, /function getRechargePayments/)
  assert.match(walletApi, /function cancelRechargePayment/)
  assert.match(rechargeOrdersPage, /order\.can_query \|\| order\.can_cancel/)
  assert.match(rechargeOrdersPage, /cancelRechargePayment\(order\.order_no, true\)/)
})

test('wrong recharge amounts can be replaced without claiming the provider order was canceled', () => {
  assert.match(walletPage, /confirmRechargeAmount\(amount\)/)
  assert.match(walletPage, /async function requestReplaceRecharge\(\)/)
  const replaceFlow = walletPage.match(/async function requestReplaceRecharge\(\)[\s\S]+?\n}\n\nfunction handleRestartRecharge/)?.[0] || ''
  assert.match(replaceFlow, /queryRechargePayment\(orderNo, true\)/)
  assert.match(replaceFlow, /paymentCardState\.value !== 'pending'/)
  assert.match(replaceFlow, /clearPaymentSession\(\)/)
  assert.doesNotMatch(replaceFlow, /cancelRechargePayment/)
})

test('recharge-facing copy identifies Qixiang Pay instead of MaPay', () => {
  assert.match(locale, /七相支付收银台/)
  assert.match(locale, /Qixiang Pay/)
  assert.doesNotMatch(locale, /码支付订单号|MaPay order|MaPay has no merchant/)
})

test('wallet removes the 0.01 test recharge and enforces production minimums', () => {
  assert.doesNotMatch(walletPage, /0\.01/)
  assert.match(walletPage, /effectiveRechargeMinimum/)
  assert.match(walletPage, /effectiveWithdrawalMinimum/)
  assert.match(walletPage, /quickAmounts = \[MINIMUM_RECHARGE_CNY, 50, 100\]/)
})
