import assert from 'node:assert/strict'
import test from 'node:test'

import {
  PAYMENT_CHECKOUT_INTERCEPT_MATCH,
  QIXIANGPAY_REFERER,
  QIXIANGPAY_RETURN_URL,
  isPaymentAppUrl,
  isPaymentReturnUrl,
  normalizePaymentCheckoutUrl,
  openH5PaymentCheckout,
  openNativePaymentCheckout,
  type NativePaymentRuntime,
  type PaymentCheckoutFailure,
} from '../src/utils/payment-checkout.ts'

interface FakeWebviewCapture {
  createdUrl: string
  id: string
  styles: Record<string, unknown>
  overrideOptions: Record<string, unknown>
  intercepted?: (event: unknown) => void
  loadedUrl: string
  loadHeaders: Record<string, string>
  animation: string
  closeAnimation: string
}

function fakeNativeRuntime() {
  const capture: FakeWebviewCapture = {
    createdUrl: '',
    id: '',
    styles: {},
    overrideOptions: {},
    loadedUrl: '',
    loadHeaders: {},
    animation: '',
    closeAnimation: '',
  }
  const opened: Array<{ url: string; fail?: (error: unknown) => void }> = []
  const runtime: NativePaymentRuntime = {
    runtime: {
      openURL(url, onError) {
        opened.push({ url, fail: onError })
      },
    },
    webview: {
      create(url, id, styles) {
        capture.createdUrl = url
        capture.id = id
        capture.styles = styles
        return {
          overrideUrlLoading(options, callback) {
            capture.overrideOptions = options
            capture.intercepted = callback
          },
          loadURL(target, headers = {}) {
            capture.loadedUrl = target
            capture.loadHeaders = headers
          },
          show(animation = '') {
            capture.animation = animation
          },
          close(animation = '') {
            capture.closeAnimation = animation
          },
        }
      },
    },
  }
  return { runtime, capture, opened }
}

test('checkout URL validation accepts only HTTPS without using the URL global', () => {
  assert.equal(normalizePaymentCheckoutUrl(' https://wod.kai.com/api/payments/qixiang/checkout/token '), 'https://wod.kai.com/api/payments/qixiang/checkout/token')
  assert.equal(normalizePaymentCheckoutUrl('http://wod.kai.com/checkout'), '')
  assert.equal(normalizePaymentCheckoutUrl('alipays://platformapi/startapp'), '')
  assert.equal(normalizePaymentCheckoutUrl('https://wod.kai.com/checkout\nmalformed'), '')
})

test('payment-app scheme matching covers Alipay and WeChat only', () => {
  for (const url of [
    'alipays://platformapi/startapp',
    'alipay://platformapi/startapp',
    'weixin://wap/pay',
  ]) {
    assert.equal(isPaymentAppUrl(url), true)
  }
  assert.equal(isPaymentAppUrl('https://qr.alipay.com/example'), false)
  assert.equal(isPaymentAppUrl('javascript:alert(1)'), false)
})

test('payment return matching accepts only the dedicated HTTPS origin and path', () => {
  assert.equal(isPaymentReturnUrl(QIXIANGPAY_RETURN_URL), true)
  assert.equal(isPaymentReturnUrl(`${QIXIANGPAY_RETURN_URL}?result=success&out_trade_no=example`), true)
  assert.equal(isPaymentReturnUrl(`${QIXIANGPAY_RETURN_URL}#complete`), true)
  assert.equal(isPaymentReturnUrl('https://wod.kai.com/account/wallet?result=success'), false)
  assert.equal(isPaymentReturnUrl('https://wod.kai.com.evil.example/payment/qixiang/return'), false)
  assert.equal(isPaymentReturnUrl('https://wod.kai.com/payment/qixiang/return/extra'), false)
  assert.equal(isPaymentReturnUrl(` ${QIXIANGPAY_RETURN_URL}`), false)
  assert.equal(isPaymentReturnUrl('kai://auth'), false)
})

test('native checkout uses a restricted internal WebView with Qixiang Referer', () => {
  const { runtime, capture } = fakeNativeRuntime()
  const target = 'https://wod.kai.com/api/payments/qixiang/checkout/token'

  assert.equal(openNativePaymentCheckout(runtime, target), true)
  assert.equal(capture.createdUrl, '')
  assert.match(capture.id, /^kai-qixiang-checkout-/)
  assert.equal(capture.styles.disablePlus, true)
  assert.equal(capture.styles.plusrequire, 'none')
  assert.equal(capture.styles['uni-app'], 'none')
  assert.deepEqual(capture.styles.additionalHttpHeaders, { Referer: QIXIANGPAY_REFERER })
  assert.deepEqual(capture.overrideOptions, {
    effect: 'instant',
    mode: 'reject',
    match: PAYMENT_CHECKOUT_INTERCEPT_MATCH,
    exclude: 'none',
  })
  assert.equal(capture.loadedUrl, target)
  assert.deepEqual(capture.loadHeaders, { Referer: QIXIANGPAY_REFERER })
  assert.equal(capture.animation, 'pop-in')
})

test('dedicated HTTPS return closes checkout once and asks the wallet to verify server state', () => {
  const { runtime, capture, opened } = fakeNativeRuntime()
  let returns = 0
  openNativePaymentCheckout(
    runtime,
    'https://wod.kai.com/api/payments/qixiang/checkout/token',
    undefined,
    () => { returns += 1 },
  )

  capture.intercepted?.({ url: `${QIXIANGPAY_RETURN_URL}?result=success` })
  capture.intercepted?.({ url: `${QIXIANGPAY_RETURN_URL}?result=failed` })
  assert.equal(capture.closeAnimation, 'none')
  assert.equal(returns, 1)
  assert.equal(opened.length, 0)
})

test('lookalike HTTPS returns never close checkout or trigger verification', () => {
  const { runtime, capture } = fakeNativeRuntime()
  let returns = 0
  openNativePaymentCheckout(
    runtime,
    'https://wod.kai.com/api/payments/qixiang/checkout/token',
    undefined,
    () => { returns += 1 },
  )

  capture.intercepted?.({ url: 'https://wod.kai.com.evil.example/payment/qixiang/return?result=success' })
  capture.intercepted?.({ url: 'https://wod.kai.com/payment/qixiang/return/extra?result=success' })
  assert.equal(capture.closeAnimation, '')
  assert.equal(returns, 0)
})

test('intercepted payment schemes go to native runtime and report launch failure', () => {
  const { runtime, capture, opened } = fakeNativeRuntime()
  const failures: PaymentCheckoutFailure[] = []
  openNativePaymentCheckout(
    runtime,
    'https://wod.kai.com/api/payments/qixiang/checkout/token',
    failure => failures.push(failure),
  )

  capture.intercepted?.({ url: 'alipays://platformapi/startapp?appId=20000067' })
  assert.equal(opened.length, 1)
  assert.equal(opened[0].url, 'alipays://platformapi/startapp?appId=20000067')
  opened[0].fail?.({ message: 'Alipay is not installed' })
  assert.equal(failures.length, 1)
  assert.equal(failures[0].code, 'payment-app-open-failed')
  assert.equal(failures[0].message, 'Alipay is not installed')
})

test('a synchronous native app launch error also reaches the failure handler', () => {
  const { runtime, capture } = fakeNativeRuntime()
  runtime.runtime.openURL = () => {
    throw new Error('No activity handles this scheme')
  }
  const failures: PaymentCheckoutFailure[] = []
  openNativePaymentCheckout(
    runtime,
    'https://wod.kai.com/api/payments/qixiang/checkout/token',
    failure => failures.push(failure),
  )

  capture.intercepted?.({ url: 'weixin://wap/pay' })
  assert.equal(failures[0]?.code, 'payment-app-open-failed')
  assert.equal(failures[0]?.message, 'No activity handles this scheme')
})

test('invalid native checkout is rejected before a WebView is created', () => {
  const { runtime, capture } = fakeNativeRuntime()
  const failures: PaymentCheckoutFailure[] = []

  assert.equal(openNativePaymentCheckout(runtime, 'alipays://platformapi/startapp', failure => failures.push(failure)), false)
  assert.equal(capture.id, '')
  assert.equal(failures[0]?.code, 'invalid-checkout-url')
})

test('H5 checkout keeps same-window location navigation', () => {
  const assigned: string[] = []
  const location = { assign: (url: string) => assigned.push(url) }
  assert.equal(openH5PaymentCheckout(location, 'https://wod.kai.com/checkout'), true)
  assert.deepEqual(assigned, ['https://wod.kai.com/checkout'])
})
