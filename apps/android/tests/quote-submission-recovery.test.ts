import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

type MockResponse = { statusCode: number; data: unknown }
type MockAttempt = { response: MockResponse } | { error: Error }

function fixture(sequence: MockAttempt[]) {
  const source = readFileSync(new URL('../src/api/request.ts', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText
  const exports: Record<string, any> = {}
  const calls: Array<Record<string, unknown>> = []
  const toasts: Array<{ title: string; icon: string }> = []
  const requireMock = (name: string) => {
    if (name === '@/utils/auth') return { getToken: () => 'session-token', clearAuth: () => {} }
    if (name === '@/utils/privacy-consent') return { requirePrivacyConsent: () => {} }
    if (name === '@/utils/auth-return-path') return { stageAuthReturnPath: () => {} }
    if (name === '@/utils/config') return { API_BASE: 'https://example.invalid/api' }
    if (name === '@/store/i18n') {
      return { useI18nStore: () => ({ locale: 'zh-TW', t: (key: string) => key, tr: (value: unknown) => String(value) }) }
    }
    throw new Error(`Unexpected dependency: ${name}`)
  }
  new Function('require', 'exports', 'uni', compiled)(requireMock, exports, {
    request: (options: Record<string, any>) => {
      calls.push(options)
      const attempt = sequence[calls.length - 1]
      assert.ok(attempt, `missing mock attempt ${calls.length}`)
      if ('error' in attempt) options.fail(attempt.error)
      else options.success(attempt.response)
    },
    showToast: (options: { title: string; icon: string }) => { toasts.push(options) },
    reLaunch: () => {},
    $emit: () => {},
  })
  return {
    request: exports.request as (options: Record<string, unknown>) => Promise<unknown>,
    calls,
    toasts,
  }
}

const success = { response: { statusCode: 200, data: { code: 0, msg: '', data: { id: 17 } } } }

test('an opted-in quote request retries one transport failure without an early toast', async () => {
  const flow = fixture([{ error: new Error('timeout') }, success])
  const data = { total_price: 120, currency: 'CNY' }
  const result = await flow.request({ url: '/buy-requests/3/quotes', method: 'POST', data, retryUncertainOnce: true })

  assert.deepEqual(result, { id: 17 })
  assert.equal(flow.calls.length, 2)
  assert.strictEqual(flow.calls[0].data, data)
  assert.strictEqual(flow.calls[1].data, data)
  assert.deepEqual(flow.toasts, [])
})

test('an opted-in quote request retries a gateway failure once', async () => {
  const flow = fixture([
    { response: { statusCode: 503, data: { code: 503, msg: 'temporary', data: null } } },
    success,
  ])

  assert.deepEqual(await flow.request({ url: '/test', retryUncertainOnce: true }), { id: 17 })
  assert.equal(flow.calls.length, 2)
  assert.deepEqual(flow.toasts, [])
})

test('validation and application errors are not retried', async () => {
  for (const statusCode of [422, 500]) {
    const flow = fixture([
      { response: { statusCode, data: { code: statusCode, msg: 'final', data: null } } },
      success,
    ])
    await assert.rejects(flow.request({ url: '/test', retryUncertainOnce: true }))
    assert.equal(flow.calls.length, 1)
    assert.equal(flow.toasts.length, 1)
  }
})

test('two transport failures stop after one retry and show one final error', async () => {
  const finalFailure = new Error('offline')
  const flow = fixture([{ error: new Error('timeout') }, { error: finalFailure }])

  await assert.rejects(flow.request({ url: '/test', retryUncertainOnce: true }), (reason) => reason === finalFailure)
  assert.equal(flow.calls.length, 2)
  assert.deepEqual(flow.toasts, [{ title: '网络异常', icon: 'none' }])
})

test('only new quote creation opts into uncertain-failure retry', () => {
  const api = readFileSync(new URL('../src/api/buy-request.ts', import.meta.url), 'utf8')
  const create = api.slice(api.indexOf('export function submitBuyRequestQuote'), api.indexOf('export function counterBuyRequestQuote'))
  const counter = api.slice(api.indexOf('export function counterBuyRequestQuote'), api.indexOf('export function withdrawBuyRequestQuote'))

  assert.match(create, /retryUncertainOnce: true/)
  assert.doesNotMatch(counter, /retryUncertainOnce/)
})
