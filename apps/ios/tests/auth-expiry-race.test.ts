import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

type RequestResponse = { statusCode: number; data: unknown }

function fixture(initialToken = 'old-session') {
  const source = readFileSync(new URL('../src/api/request.ts', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText
  const exports: Record<string, any> = {}
  const requests: Array<{ success: (result: RequestResponse) => void }> = []
  const uploads: Array<{ success: (result: RequestResponse) => void }> = []
  let currentToken = initialToken
  let cleared = 0
  let emitted = 0
  let redirected = 0
  let staged = 0

  const requireMock = (name: string) => {
    if (name === '@/utils/auth') {
      return {
        getToken: () => currentToken,
        clearAuth: () => {
          cleared += 1
          currentToken = ''
        },
      }
    }
    if (name === '@/utils/privacy-consent') return { requirePrivacyConsent: () => {} }
    if (name === '@/utils/auth-return-path') return { stageAuthReturnPath: () => { staged += 1 } }
    if (name === '@/utils/config') return { API_BASE: 'https://example.invalid/api' }
    if (name === '@/store/i18n') {
      return {
        useI18nStore: () => ({
          locale: 'zh-CN',
          t: (key: string) => key,
          tr: (value: unknown) => String(value),
        }),
      }
    }
    throw new Error(`Unexpected dependency: ${name}`)
  }

  new Function('require', 'exports', 'uni', compiled)(requireMock, exports, {
    request: (options: { success: (result: RequestResponse) => void }) => requests.push(options),
    uploadFile: (options: { success: (result: RequestResponse) => void }) => {
      uploads.push(options)
      return { onProgressUpdate: () => {} }
    },
    downloadFile: () => {},
    showToast: () => {},
    reLaunch: () => { redirected += 1 },
    $emit: () => { emitted += 1 },
  })

  return {
    request: exports.request as (options: Record<string, unknown>) => Promise<unknown>,
    upload: exports.upload as (options: Record<string, unknown>) => Promise<unknown>,
    respondRequest: (index: number, result: RequestResponse) => requests[index].success(result),
    respondUpload: (index: number, result: RequestResponse) => uploads[index].success(result),
    setToken: (token: string) => { currentToken = token },
    token: () => currentToken,
    cleared: () => cleared,
    emitted: () => emitted,
    redirected: () => redirected,
    staged: () => staged,
  }
}

test('a late 401 from an old request cannot clear a newly signed-in session', async () => {
  const flow = fixture()
  const pending = flow.request({ url: '/assets' })
  flow.setToken('new-session')
  flow.respondRequest(0, { statusCode: 401, data: { code: 401, msg: 'expired' } })

  await assert.rejects(pending, /未登录/)
  assert.equal(flow.token(), 'new-session')
  assert.equal(flow.cleared(), 0)
  assert.equal(flow.emitted(), 0)
  assert.equal(flow.redirected(), 0)
  assert.equal(flow.staged(), 0)
})

test('concurrent 401 responses expire the current session only once', async () => {
  const flow = fixture('same-session')
  const first = flow.request({ url: '/assets' })
  const second = flow.request({ url: '/orders' })

  flow.respondRequest(0, { statusCode: 401, data: { code: 401 } })
  flow.respondRequest(1, { statusCode: 401, data: { code: 401 } })
  await Promise.all([assert.rejects(first), assert.rejects(second)])

  assert.equal(flow.token(), '')
  assert.equal(flow.cleared(), 1)
  assert.equal(flow.emitted(), 1)
  assert.equal(flow.redirected(), 1)
  assert.equal(flow.staged(), 1)
})

test('a late 401 from an old upload cannot clear a newly signed-in session', async () => {
  const flow = fixture()
  const pending = flow.upload({ url: '/community/upload', filePath: 'video.mp4' })
  flow.setToken('new-session')
  flow.respondUpload(0, { statusCode: 401, data: JSON.stringify({ code: 401, msg: 'expired' }) })

  await assert.rejects(pending, /未登录/)
  assert.equal(flow.token(), 'new-session')
  assert.equal(flow.cleared(), 0)
  assert.equal(flow.emitted(), 0)
  assert.equal(flow.redirected(), 0)
  assert.equal(flow.staged(), 0)
})

test('a current upload 401 still expires the active session', async () => {
  const flow = fixture('upload-session')
  const pending = flow.upload({ url: '/community/upload', filePath: 'video.mp4' })
  flow.respondUpload(0, { statusCode: 401, data: JSON.stringify({ code: 401, msg: 'expired' }) })

  await assert.rejects(pending, /未登录/)
  assert.equal(flow.token(), '')
  assert.equal(flow.cleared(), 1)
  assert.equal(flow.emitted(), 1)
  assert.equal(flow.redirected(), 1)
  assert.equal(flow.staged(), 1)
})

test('an empty-token 401 redirects only while no newer session exists', async () => {
  const currentGuest = fixture('')
  const currentPending = currentGuest.request({ url: '/assets' })
  currentGuest.respondRequest(0, { statusCode: 401, data: { code: 401 } })
  await assert.rejects(currentPending, /未登录/)
  assert.equal(currentGuest.cleared(), 1)
  assert.equal(currentGuest.emitted(), 1)
  assert.equal(currentGuest.redirected(), 1)
  assert.equal(currentGuest.staged(), 1)

  const staleGuest = fixture('')
  const stalePending = staleGuest.request({ url: '/assets' })
  staleGuest.setToken('new-session')
  staleGuest.respondRequest(0, { statusCode: 401, data: { code: 401 } })
  await assert.rejects(stalePending, /未登录/)
  assert.equal(staleGuest.token(), 'new-session')
  assert.equal(staleGuest.cleared(), 0)
  assert.equal(staleGuest.emitted(), 0)
  assert.equal(staleGuest.redirected(), 0)
  assert.equal(staleGuest.staged(), 0)
})
