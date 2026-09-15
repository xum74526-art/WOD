import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import {
  AUTH_RETURN_PATH_STORAGE_KEY,
  AUTH_RETURN_PATH_TTL_MS,
  buildAuthReturnPath,
  consumeAuthReturnPath,
  normalizeAuthReturnPath,
  stageAuthReturnPath,
} from '../src/utils/auth-return-path.ts'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

test('only registered internal pages and bounded business query fields can be restored', () => {
  assert.equal(buildAuthReturnPath('pages/order/detail', { id: 42, token: 'secret' }), '/pages/order/detail?id=42')
  assert.equal(
    buildAuthReturnPath('/pages/buy-request/index', { compose: 1, view: 'seller', scope: 'quoted' }),
    '/pages/buy-request/index?compose=1&view=seller&scope=quoted',
  )
  assert.equal(buildAuthReturnPath('pages/assets/index', { panel: 'expiry-maintenance' }), '/pages/assets/index?panel=expiry-maintenance')
  assert.equal(buildAuthReturnPath('pages/devices/index', { status: 'action_required' }), '/pages/devices/index?status=action_required')
  assert.equal(buildAuthReturnPath('pages/quote/index', { model: 'H100 80GB', variant: 'SXM5' }), '/pages/quote/index?model=H100%2080GB&variant=SXM5')

  for (const route of [
    'pages/login/index',
    'pages/forgot-password/index',
    'pages/reset-password/index',
    'pages/agreement/index',
    'pages/account-deletion/index',
    'pages/password/index',
    'pages/recovery-email/index',
    'pages/verification/index',
    'pages/bank-cards/index',
    'pages/ui-preview-v12/index',
    'pages/not-registered/index',
    'https://evil.example/',
  ]) assert.equal(buildAuthReturnPath(route, {}), null)

  for (const route of [
    'pages/community/detail',
    'pages/product/detail',
    'pages/asset/detail',
    'pages/order/detail',
    'pages/withdrawals/detail',
    'pages/store/index',
  ]) {
    assert.equal(buildAuthReturnPath(route), null)
    assert.equal(normalizeAuthReturnPath(`/${route}`), null)
  }
  assert.equal(buildAuthReturnPath('pages/order/detail', { id: 0 }), null)
  assert.equal(normalizeAuthReturnPath('/pages/order/detail?id=42'), '/pages/order/detail?id=42')
  assert.equal(normalizeAuthReturnPath('/pages/order/detail?id=42&token=secret'), null)
  assert.equal(normalizeAuthReturnPath('/pages/order/detail?id=42&id=43'), null)
  assert.equal(normalizeAuthReturnPath('//evil.example/pages/order/detail?id=42'), null)
  assert.equal(normalizeAuthReturnPath('/pages/order/detail?id=42#fragment'), null)
  assert.equal(normalizeAuthReturnPath('/pages/quote/index?model=%5Cevil'), null)
  assert.equal(buildAuthReturnPath('pages/assets/index', { panel: 'admin' }), null)
  assert.equal(buildAuthReturnPath('pages/devices/index', { status: 'deleted' }), null)
  assert.equal(buildAuthReturnPath('pages/quote/index', { model: '<script>/?x=1' }), null)
  assert.equal(buildAuthReturnPath('pages/quote/index', { model: 'H100', variant: '' }), '/pages/quote/index?model=H100')
  assert.equal(normalizeAuthReturnPath('/pages/quote/index?model=H100&variant='), '/pages/quote/index?model=H100')
  assert.equal(normalizeAuthReturnPath('/pages/quote/index?model=&variant=SXM5'), null)
  assert.equal(buildAuthReturnPath('pages/wallet/index', { withdraw: 1, rechargeAmount: '500', rechargeChannel: 'alipay' }), '/pages/wallet/index')
  assert.equal(normalizeAuthReturnPath('/pages/wallet/index?withdraw=1'), null)
  assert.equal(normalizeAuthReturnPath('/pages/index/index?id=1'), null)
})

test('a staged return path is short-lived, one-shot and omits unknown page options', () => {
  const previousUni = (globalThis as any).uni
  const previousGetCurrentPages = (globalThis as any).getCurrentPages
  const storage = new Map<string, unknown>()
  let currentPage: Record<string, unknown> = {
    route: 'pages/asset/detail',
    options: { id: '77', ticket: 'must-not-persist' },
  }
  ;(globalThis as any).uni = {
    setStorageSync: (key: string, value: unknown) => storage.set(key, value),
    getStorageSync: (key: string) => storage.get(key),
    removeStorageSync: (key: string) => storage.delete(key),
  }
  ;(globalThis as any).getCurrentPages = () => [currentPage]
  try {
    assert.equal(stageAuthReturnPath(1_000), '/pages/asset/detail?id=77')
    assert.ok(storage.has(AUTH_RETURN_PATH_STORAGE_KEY))
    assert.equal(consumeAuthReturnPath(1_001), '/pages/asset/detail?id=77')
    assert.equal(consumeAuthReturnPath(1_002), null)

    currentPage = {
      route: 'pages/index/index',
      $page: { fullPath: '/pages/order/detail?id=42' },
    }
    assert.equal(stageAuthReturnPath(2_000), '/pages/order/detail?id=42')
    assert.equal(consumeAuthReturnPath(2_001), '/pages/order/detail?id=42')

    currentPage = {
      route: 'pages/product/detail',
      $page: { options: { id: '9', token: 'must-not-persist' } },
    }
    assert.equal(stageAuthReturnPath(3_000), '/pages/product/detail?id=9')
    assert.equal(consumeAuthReturnPath(3_001), '/pages/product/detail?id=9')
  } finally {
    ;(globalThis as any).uni = previousUni
    ;(globalThis as any).getCurrentPages = previousGetCurrentPages
  }
})

test('expired, implausibly long-lived and tampered records are removed without navigation', () => {
  const previousUni = (globalThis as any).uni
  let stored: unknown = null
  ;(globalThis as any).uni = {
    getStorageSync: () => stored,
    removeStorageSync: () => { stored = null },
  }
  try {
    stored = { path: '/pages/order/detail?id=9', expiresAt: 999 }
    assert.equal(consumeAuthReturnPath(1_000), null)
    assert.equal(stored, null)

    stored = { path: '/pages/order/detail?id=9', expiresAt: 1_000 + AUTH_RETURN_PATH_TTL_MS + 1 }
    assert.equal(consumeAuthReturnPath(1_000), null)
    assert.equal(stored, null)

    stored = { path: 'https://evil.example/', expiresAt: 1_001 }
    assert.equal(consumeAuthReturnPath(1_000), null)
    assert.equal(stored, null)
  } finally {
    ;(globalThis as any).uni = previousUni
  }
})

test('401 staging and successful-login navigation preserve inquiry priority without replay', () => {
  const request = source('../src/api/request.ts')
  const login = source('../src/pages/login/index.vue')
  const store = source('../src/store/user.ts')
  const expireStart = request.indexOf('function expireSession')
  const expireEnd = request.indexOf('function errorMessage', expireStart)
  const expireFlow = request.slice(expireStart, expireEnd)
  assert.ok(expireStart >= 0 && expireEnd > expireStart)
  assert.ok(expireFlow.indexOf('getToken() !== requestToken') < expireFlow.indexOf('stageAuthReturnPath()'))
  assert.ok(expireFlow.indexOf('stageAuthReturnPath()') < expireFlow.indexOf('clearAuth()'))

  const enterStart = login.indexOf('function enterAuthenticatedApp()')
  const enterEnd = login.indexOf('function runtimeKaiCallback()', enterStart)
  const enterFlow = login.slice(enterStart, enterEnd)
  assert.match(enterFlow, /if \(authenticatedNavigationStarted\) return/)
  assert.ok(enterFlow.indexOf('consumeAuthReturnPath()') < enterFlow.indexOf('hasInquiryRequestPrefill()'))
  assert.match(enterFlow, /hasInquiryRequestPrefill\(\)[\s\S]*\/pages\/buy-request\/index\?compose=1/)
  assert.match(enterFlow, /if \(returnPath\)[\s\S]*url: returnPath[\s\S]*fail: \(\) => uni\.reLaunch\(\{ url: '\/pages\/index\/index' \}\)/)
  assert.doesNotMatch(store, /stageAuthReturnPath/)
})
