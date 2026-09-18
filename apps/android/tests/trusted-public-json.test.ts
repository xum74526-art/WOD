import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

function transportFixture(response: { statusCode: number; data: unknown }) {
  const source = readFileSync(new URL('../src/api/request.ts', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText
  const exports: Record<string, any> = {}
  const requests: Record<string, any>[] = []
  const requireMock = (name: string) => {
    if (name === '@/utils/auth') return { getToken: () => 'private-session', clearAuth: () => {} }
    if (name === '@/utils/privacy-consent') return { requirePrivacyConsent: () => {} }
    if (name === '@/utils/auth-return-path') return { stageAuthReturnPath: () => {} }
    if (name === '@/utils/config') return { API_BASE: 'https://wod.kai.com/api' }
    if (name === '@/store/i18n') return { useI18nStore: () => ({ locale: 'zh-CN', t: (key: string) => key, tr: (value: string) => value }) }
    throw new Error(`Unexpected dependency: ${name}`)
  }
  new Function('require', 'exports', 'uni', compiled)(requireMock, exports, {
    request(options: Record<string, any>) {
      requests.push(options)
      options.success(response)
    },
  })
  return {
    requestTrustedPublicJson: exports.requestTrustedPublicJson as (options: Record<string, unknown>) => Promise<unknown>,
    requests,
  }
}

test('trusted public JSON transport permits only credential-free Bilibili metadata GETs', async () => {
  const flow = transportFixture({ statusCode: 200, data: { code: 0 } })
  const data = await flow.requestTrustedPublicJson({
    url: 'https://api.bilibili.com/x/player/pagelist?bvid=BV1Ab411C7De',
    timeout: 30_000,
    header: {
      Referer: 'https://www.bilibili.com/',
      'User-Agent': 'Mozilla/5.0',
    },
  })
  assert.deepEqual(data, { code: 0 })
  assert.equal(flow.requests.length, 1)
  assert.equal(flow.requests[0].method, 'GET')
  assert.equal(flow.requests[0].timeout, 15_000)
  assert.deepEqual(flow.requests[0].header, {
    Referer: 'https://www.bilibili.com/',
    'User-Agent': 'Mozilla/5.0',
  })
  assert.equal(flow.requests[0].header.Authorization, undefined)
})

test('trusted public JSON transport rejects other origins and unsafe headers before networking', async () => {
  const flow = transportFixture({ statusCode: 200, data: {} })
  for (const url of [
    'http://api.bilibili.com/x/player/pagelist',
    'https://api.bilibili.com.evil.example/x/player/pagelist',
    'https://user@api.bilibili.com/x/player/pagelist',
    'https://api.bilibili.com:443/x/player/pagelist',
  ]) {
    await assert.rejects(flow.requestTrustedPublicJson({ url }), /Untrusted public JSON request URL/)
  }
  await assert.rejects(flow.requestTrustedPublicJson({
    url: 'https://api.bilibili.com/x/player/pagelist',
    header: { Authorization: 'private-session' },
  }), /Untrusted public JSON request header/)
  assert.equal(flow.requests.length, 0)
})

test('trusted public JSON transport rejects non-success HTTP responses', async () => {
  const flow = transportFixture({ statusCode: 503, data: {} })
  await assert.rejects(flow.requestTrustedPublicJson({
    url: 'https://api.bilibili.com/x/player/pagelist',
  }), /HTTP 503/)
})
