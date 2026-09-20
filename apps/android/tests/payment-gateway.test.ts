import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const walletApi = readFileSync(new URL('../src/api/wallet.ts', import.meta.url), 'utf8')
const walletPage = readFileSync(new URL('../src/pages/wallet/index.vue', import.meta.url), 'utf8')
const walletActions = readFileSync(new URL('../src/components/direct-trade/DirectTradeWalletActions.vue', import.meta.url), 'utf8')
const checkout = readFileSync(new URL('../src/utils/payment-checkout.ts', import.meta.url), 'utf8')
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
  assert.match(rechargeOrdersPage, /rechargeCanQuery\(order\) \|\| rechargeCanCancel\(order\)/)
  assert.match(rechargeOrdersPage, /cancelRechargePayment\(order\.order_no, true\)/)
})

test('wallet keeps historical query and cancellation without opening a new recharge', () => {
  assert.match(walletPage, /queryRechargePayment\(orderNo, true\)/)
  assert.match(walletPage, /cancelRechargePayment\(paymentSession\.value\.orderNo, true\)/)
  assert.doesNotMatch(walletPage, /createRechargePayment|requestReplaceRecharge|handleRestartRecharge|continueCurrentPayment/)
  assert.doesNotMatch(rechargeOrdersPage, /restartOrder|restartRecharge|createRechargeRestartRoute/)
})

test('native payment return closes only on the dedicated HTTPS route and triggers server verification', () => {
  assert.match(checkout, /QIXIANGPAY_RETURN_URL = 'https:\/\/wod\.kai\.com\/payment\/qixiang\/return'/)
  assert.match(walletActions, /\(\) => emit\('paymentReturned'\)/)
  assert.match(walletPage, /@payment-returned="handleDirectPaymentReturned"/)
  assert.match(walletPage, /handleDirectPaymentReturned\(\)[\s\S]*?refreshPendingPayment\(false, true\)/)
  assert.match(walletPage, /server-authoritative/)
})

test('recharge-facing copy identifies Qixiang Pay instead of MaPay', () => {
  assert.match(locale, /七相支付收银台/)
  assert.match(locale, /Qixiang Pay/)
  assert.doesNotMatch(locale, /码支付订单号|MaPay order|MaPay has no merchant/)
})

test('wallet hides all new recharge and withdrawal entry points', () => {
  assert.doesNotMatch(walletPage, /0\.01/)
  assert.doesNotMatch(walletPage, /createRechargePayment|createWithdrawal|openRecharge|openWithdraw|payAndRecharge/)
  assert.match(walletPage, /goRechargeOrders/)
  assert.match(walletPage, /goWithdrawals/)
})
