import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
import * as vue from 'vue'
import * as accountCache from '../src/utils/payment-account-storage.ts'
import * as recharge from '../src/utils/recharge-payment.ts'
import * as intents from '../src/utils/financial-request-intent.ts'

const KEY = 'wod-pending-recharge-order'
const INTENT = 'wod-recharge-request-intent'
function memory() {
  const values = new Map<string, unknown>()
  return {
    values,
    getStorageSync: (key: string) => values.get(key),
    setStorageSync: (key: string, value: unknown) => { values.set(key, value) },
    removeStorageSync: (key: string) => { values.delete(key) },
  }
}
function session(orderNo = 'ORDER-A') {
  return { version: 1, orderNo, checkoutUrl: 'https://example.invalid/checkout', fallbackExpiresAtMs: Date.now() + 300000, successNotified: false, amountCny: 10, paymentType: 'wxpay' }
}
function deferred<T = any>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

test('switching accounts cannot reuse another account’s order or request id', () => {
  const storage = memory()
  const current = { userId: 11, token: 'token-a' }
  const a = accountCache.createPaymentAccountStorage(storage, () => current)
  a.setStorageSync(KEY, session())
  const intent = intents.ensureClientRequestIntent(null, '10.00|wxpay', 'request-00000001')
  a.setStorageSync(INTENT, intent)
  const same = accountCache.createPaymentAccountStorage(storage, () => current)
  assert.equal(recharge.readStoredRechargeSession(same.getStorageSync(KEY))?.orderNo, 'ORDER-A')
  assert.equal(intents.ensureClientRequestIntent(same.getStorageSync(INTENT), '10.00|wxpay', 'request-00000002').requestId, intent.requestId)

  // Mutate the same identity object to verify the guard captured a snapshot.
  current.userId = 22; current.token = 'token-b'
  const b = accountCache.createPaymentAccountStorage(storage, () => current)
  assert.equal(b.getStorageSync(KEY), undefined)
  assert.equal(b.getStorageSync(INTENT), undefined)
  b.setStorageSync(KEY, session('ORDER-B'))
  a.setStorageSync(KEY, session('LATE-A'))
  a.removeStorageSync(KEY)
  assert.equal(recharge.readStoredRechargeSession(b.getStorageSync(KEY))?.orderNo, 'ORDER-B')
  assert.equal(a.isCurrent(), false)
})

test('legacy unowned records are discarded; logout also clears scoped financial intents', () => {
  const storage = memory()
  for (const key of accountCache.PAYMENT_CACHE_KEYS) storage.setStorageSync(key, session())
  storage.setStorageSync('locale', 'en')
  const cache = accountCache.createPaymentAccountStorage(storage, () => ({ userId: 22, token: 'token-b' }))
  assert.equal(cache.getStorageSync(KEY), undefined)
  for (const key of accountCache.PAYMENT_CACHE_KEYS) {
    assert.equal(storage.getStorageSync(key), undefined)
    cache.setStorageSync(key, session())
  }
  accountCache.clearPaymentAccountStorage(storage)
  assert.deepEqual([...storage.values], [['locale', 'en']])
})

test('logout and token replacement invalidate financial state without clearing preferences', () => {
  const storage = memory()
  const source = readFileSync(new URL('../src/utils/auth.ts', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const auth: any = {}
  new Function('require', 'exports', 'uni', compiled)(() => accountCache, auth, storage)
  auth.setToken('first-session')
  const first = accountCache.createPaymentAccountStorage(storage, () => ({ userId: 11, token: auth.getToken() }))
  first.setStorageSync(KEY, session())
  auth.setToken('second-session')
  assert.equal(first.isCurrent(), false)
  assert.equal([...storage.values.keys()].some(key => key.startsWith(KEY)), false)
  auth.clearAuth()
  assert.equal(auth.getToken(), '')
})

class RequestError extends Error {
  statusCode: number
  constructor(code: number) { super(String(code)); this.statusCode = code }
}

// Execute the real Vue setup code with mocked network/native boundaries. No
// live recharge, payment-provider query or account mutation is performed.
function fixture(kind: 'wallet' | 'actions' = 'wallet', api: Record<string, any> = {}) {
  const storage = memory()
  const user = vue.reactive({ token: 'token-a', userInfo: { id: 11 } })
  const scope = vue.effectScope()
  const events: string[] = []
  const notices: any[] = []
  let checkoutCount = 0
  const path = kind === 'wallet' ? '../src/pages/wallet/index.vue' : '../src/components/direct-trade/DirectTradeWalletActions.vue'
  const source = readFileSync(new URL(path, import.meta.url), 'utf8').split('<script setup lang="ts">')[1].split('</script>')[0]
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText
  const props = { wallet: { recharge_service_enabled: true, payment_config: { enabled: true, payment_types: ['alipay', 'wxpay'], min_amount_cny: 10 } } }
  const modules: Record<string, any> = {
    vue: { ...vue, onMounted() {}, onUnmounted() {} },
    '@dcloudio/uni-app': { onLoad() {}, onShow() {}, onHide() {}, onUnload() {} },
    '@/api/wallet': api,
    '@/api/withdrawal': api,
    '@/api/request': { ApiRequestError: RequestError },
    '@/store/user': { useUserStore: () => user },
    '@/store/asset': { useAssetStore: () => ({ refresh: async () => {} }) },
    '@/store/commerce': { useCommerceStore: () => ({ rechargeEnabled: true, historyReadEnabled: true }) },
    '@/store/i18n': { useI18nStore: () => ({ t: (key: string) => key, tr: (value: string) => value }) },
    '@/utils/auth': { getToken: () => user.token },
    '@/utils/payment-account-storage': accountCache,
    '@/utils/recharge-payment': recharge,
    '@/utils/financial-request-intent': intents,
    '@/utils/config': { resolveBackendUrl: (value: string) => value },
    '@/utils/format': { formatNumberInput: String },
    '@/utils/payment-checkout': { openPaymentCheckout: () => { checkoutCount += 1 } },
  }
  const exposed = kind === 'wallet'
    ? 'hydratePaymentSession, refreshPendingPayment, paymentSession, pendingPayment, checkingStatus, fetchWallet, wallet'
    : 'openRecharge, sheet, submitRecharge, submitting'
  const flow = scope.run(() => new Function('require', 'exports', 'uni', 'defineProps', 'defineEmits', `${compiled}\nreturn {${exposed}}`)(
    (name: string) => modules[name] || {}, {},
    { ...storage, showToast: (value: any) => notices.push(value), showModal: (value: any) => notices.push(value) },
    () => props, () => (event: string) => events.push(event),
  ))
  const cache = () => accountCache.createPaymentAccountStorage(storage, () => ({ userId: user.userInfo.id, token: user.token }))
  return { flow, storage, user, events, notices, cache, checkoutCount: () => checkoutCount, stop: () => scope.stop() }
}

test('wallet clears missing or forbidden cached orders but keeps recovery after network failures', async () => {
  for (const code of [403, 404, 503]) {
    const f = fixture('wallet', { getRechargePayment: async () => { throw new RequestError(code) } })
    try {
      f.cache().setStorageSync(KEY, session())
      await f.flow.refreshPendingPayment(true, false)
      assert.equal(Boolean(f.flow.paymentSession.value), code === 503)
      assert.equal(Boolean(f.cache().getStorageSync(KEY)), code === 503)
      assert.equal(f.flow.checkingStatus.value, false)
    } finally { f.stop() }
  }
})

test('cached wallet page resets on account switch and discards late order and balance responses', async () => {
  const order = deferred()
  const balance = deferred()
  const f = fixture('wallet', { getRechargePayment: () => order.promise, getWallet: () => balance.promise })
  try {
    f.cache().setStorageSync(KEY, session())
    const pendingOrder = f.flow.refreshPendingPayment(false, false)
    const pendingWallet = f.flow.fetchWallet()
    f.user.token = 'token-b'; f.user.userInfo = { id: 22 }
    assert.equal(f.flow.paymentSession.value, null)
    f.cache().setStorageSync(KEY, session('ORDER-B'))
    order.resolve({ order_no: 'ORDER-A', status: 'paid', credited_at: '2026-10-01' })
    balance.resolve({ balance: 9999 })
    await Promise.all([pendingOrder, pendingWallet])
    assert.equal(f.flow.wallet.value, null)
    assert.equal(f.flow.pendingPayment.value, null)
    assert.equal(f.flow.checkingStatus.value, false)
    assert.equal(recharge.readStoredRechargeSession(f.cache().getStorageSync(KEY))?.orderNo, 'ORDER-B')
    assert.equal(f.notices.length, 0)
  } finally { f.stop() }
})

test('new account can start the same recharge without inheriting a duplicate-order alert', async () => {
  let calls = 0
  const f = fixture('actions', { createRechargePayment: async () => { calls += 1; return { order_no: 'ORDER-B', checkout_url: 'https://example.invalid/checkout' } } })
  try {
    f.cache().setStorageSync(KEY, session())
    f.user.token = 'token-b'; f.user.userInfo = { id: 22 }
    f.flow.openRecharge(); f.flow.sheet.amount = '10'; f.flow.sheet.paymentType = 'wxpay'
    await f.flow.submitRecharge()
    assert.equal(calls, 1)
    assert.equal(f.checkoutCount(), 1)
    assert.deepEqual(f.events, ['paymentStarted'])
    assert.equal(f.notices.length, 0)
  } finally { f.stop() }
})

test('an old recharge response cannot reopen checkout or overwrite the new account’s session', async () => {
  const response = deferred()
  const f = fixture('actions', { createRechargePayment: () => response.promise })
  try {
    f.flow.openRecharge(); f.flow.sheet.amount = '10'
    const pending = f.flow.submitRecharge()
    f.user.token = 'token-b'; f.user.userInfo = { id: 22 }
    f.cache().setStorageSync(KEY, session('ORDER-B'))
    response.resolve({ order_no: 'ORDER-A', checkout_url: 'https://example.invalid/checkout' })
    await pending
    assert.equal(f.checkoutCount(), 0)
    assert.deepEqual(f.events, [])
    assert.equal(f.flow.sheet.type, '')
    assert.equal(recharge.readStoredRechargeSession(f.cache().getStorageSync(KEY))?.orderNo, 'ORDER-B')
  } finally { f.stop() }
})

test('the current account still gets duplicate protection for its own pending recharge', async () => {
  let calls = 0
  const f = fixture('actions', { createRechargePayment: async () => { calls += 1 } })
  try {
    f.cache().setStorageSync(KEY, session())
    f.flow.openRecharge()
    if (f.flow.sheet.type === 'recharge') {
      f.flow.sheet.amount = '10'; f.flow.sheet.paymentType = 'wxpay'
      await f.flow.submitRecharge()
    }
    assert.equal(calls, 0)
    assert.ok(f.notices.some(notice => notice.title === 'activeRechargeExistsTitle'))
    assert.equal(f.checkoutCount(), 0)
  } finally { f.stop() }
})
