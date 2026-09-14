import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

type MockResponse = { statusCode: number; data: unknown }

function fixture(response: MockResponse) {
  const source = readFileSync(new URL('../src/api/request.ts', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText
  const exports: Record<string, any> = {}
  const toasts: Array<{ title: string; icon: string }> = []
  const translated: unknown[] = []
  let cleared = 0
  let redirected = 0
  const messages: Record<string, string> = {
    requestValidationFailed: '提交内容格式不正确，请检查后重试。',
    '请求失败': '请求失败',
  }
  const requireMock = (name: string) => {
    if (name === '@/utils/auth') {
      return { getToken: () => 'session-token', clearAuth: () => { cleared += 1 } }
    }
    if (name === '@/utils/config') return { API_BASE: 'https://example.invalid/api' }
    if (name === '@/store/i18n') {
      return {
        useI18nStore: () => ({
          locale: 'zh-CN',
          t: (key: string) => messages[key] || key,
          tr: (value: unknown) => {
            translated.push(value)
            assert.equal(typeof value, 'string')
            return value === '业务提示' ? '已本地化业务提示' : value
          },
        }),
      }
    }
    throw new Error(`Unexpected dependency: ${name}`)
  }
  new Function('require', 'exports', 'uni', compiled)(requireMock, exports, {
    request: (options: { success: (result: MockResponse) => void }) => options.success(response),
    showToast: (options: { title: string; icon: string }) => { toasts.push(options) },
    reLaunch: () => { redirected += 1 },
    $emit: () => {},
  })
  return {
    request: exports.request as (options: Record<string, unknown>) => Promise<unknown>,
    ApiRequestError: exports.ApiRequestError as new (...args: any[]) => Error & { statusCode: number },
    toasts,
    translated,
    cleared: () => cleared,
    redirected: () => redirected,
  }
}

test('structured 422 validation errors use a safe localized message', async () => {
  const flow = fixture({
    statusCode: 422,
    data: {
      detail: [{
        type: 'string_pattern_mismatch',
        loc: ['body', 'phone'],
        msg: 'String should match pattern',
        input: 'private-input',
      }],
    },
  })
  const expected = '提交内容格式不正确，请检查后重试。'
  await assert.rejects(flow.request({ url: '/test' }), (error: any) => {
    assert.ok(error instanceof flow.ApiRequestError)
    assert.equal(error.statusCode, 422)
    assert.equal(error.message, expected)
    assert.doesNotMatch(error.message, /\[object Object\]|phone|private-input|String should match pattern/)
    return true
  })
  assert.deepEqual(flow.toasts, [{ title: expected, icon: 'none' }])
  assert.deepEqual(flow.translated, [expected])
  assert.equal(flow.cleared(), 0)
  assert.equal(flow.redirected(), 0)
})

test('safe string business messages keep precedence over string detail', async () => {
  const messageFlow = fixture({
    statusCode: 422,
    data: { msg: '  业务提示  ', detail: '详细提示' },
  })
  await assert.rejects(messageFlow.request({ url: '/test' }), (error: any) => {
    assert.equal(error.message, '已本地化业务提示')
    return true
  })
  assert.deepEqual(messageFlow.translated, ['业务提示'])

  const detailFlow = fixture({
    statusCode: 422,
    data: { msg: '   ', detail: '  详细提示  ' },
  })
  await assert.rejects(detailFlow.request({ url: '/test' }), (error: any) => {
    assert.equal(error.message, '详细提示')
    return true
  })
  assert.deepEqual(detailFlow.translated, ['详细提示'])
})

test('malformed non-validation errors use the ordinary request fallback', async () => {
  const flow = fixture({
    statusCode: 500,
    data: { msg: { internal: true }, detail: { trace: 'do-not-display' } },
  })
  await assert.rejects(flow.request({ url: '/test' }), (error: any) => {
    assert.equal(error.statusCode, 500)
    assert.equal(error.message, '请求失败')
    assert.doesNotMatch(error.message, /\[object Object\]|trace|internal/)
    return true
  })
  assert.deepEqual(flow.toasts, [{ title: '请求失败', icon: 'none' }])
})

test('silent validation errors still reject without showing a toast', async () => {
  const flow = fixture({ statusCode: 422, data: { detail: [{ loc: ['body', 'email'] }] } })
  await assert.rejects(flow.request({ url: '/test', silent: true }), (error: any) => {
    assert.equal(error.statusCode, 422)
    assert.equal(error.message, '提交内容格式不正确，请检查后重试。')
    return true
  })
  assert.deepEqual(flow.toasts, [])
})
