import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import {
  createDeletionController, createDeletionState, validDeletionReceipt,
  DELETION_RECEIPT_TTL_MS, type DeletionReceipt, type DeletionResult,
} from '../src/utils/account-deletion.ts'
import { parseKaiAuthUrl } from '../src/utils/kai-auth-callback.ts'
import {
  beginDeletionKaiReauth, stageDeletionKaiCallback, takePendingDeletionKaiCallback,
} from '../src/utils/account-deletion-kai-callback.ts'

const now = Date.parse('2026-09-04T10:00:00Z')
function fixture() {
  const state = createDeletionState()
  const calls: string[] = []
  let receipt: DeletionReceipt | null = null
  let result: DeletionResult = { status: 'processing', blockers: [], completed_at: null }
  let failSubmit = false
  let submitHold: Promise<void> | null = null
  const controller = createDeletionController({
    state, now: () => now,
    eligibility: async () => { calls.push('eligibility'); return { eligible: true, blockers: [], automatic_actions: ['Remove unmatched requests'], verification_methods: ['password', 'kai'] } },
    verify: async (password) => { assert.equal(password, 'test-password'); calls.push('verify'); return { ticket: 'deletion-only-test-capability', expires_at: new Date(now + 600_000).toISOString() } },
    verifyKai: async (token) => { assert.equal(token, 'kai-deletion-proof'); calls.push('verify-kai'); return { ticket: 'deletion-only-test-capability', expires_at: new Date(now + 600_000).toISOString() } },
    submit: async (ticket) => { assert.equal(ticket, 'deletion-only-test-capability'); calls.push('submit'); if (submitHold) await submitHold; if (failSubmit) throw new Error('timeout'); return result },
    status: async (ticket) => { assert.equal(ticket, 'deletion-only-test-capability'); calls.push('status'); return result },
    saveReceipt: (value) => { calls.push('save'); receipt = value },
    clearReceipt: () => { calls.push('clear-receipt'); receipt = null },
    clearSession: () => { calls.push('logout') },
  })
  return { state, calls, controller, receipt: () => receipt, result: (next: DeletionResult) => { result = next }, fail: () => { failSubmit = true }, hold: (next: Promise<void>) => { submitHold = next } }
}

test('KAI deletion callback accepts only the app fragment and stages its proof in memory once', async () => {
  assert.equal(parseKaiAuthUrl('https://evil.example/#kai_deletion_token=stolen'), null)
  assert.equal(parseKaiAuthUrl('kai://auth?kai_deletion_token=query-leak'), null)
  const callback = parseKaiAuthUrl('kai://auth#kai_deletion_token=kai-deletion-proof')
  assert.deepEqual(callback, { deletionToken: 'kai-deletion-proof' })
  assert.equal(stageDeletionKaiCallback(callback), true)
  assert.deepEqual(takePendingDeletionKaiCallback(), { token: 'kai-deletion-proof' })
  assert.equal(takePendingDeletionKaiCallback(), null)
  assert.equal(stageDeletionKaiCallback(callback), false)
  beginDeletionKaiReauth()
  assert.equal(stageDeletionKaiCallback(parseKaiAuthUrl('kai://auth?kai_error=access_denied')), true)
  assert.deepEqual(takePendingDeletionKaiCallback(), { error: 'access_denied' })

  const flow = fixture()
  await flow.controller.checkEligibility()
  await flow.controller.verifyKai('kai-deletion-proof')
  assert.equal(flow.state.stage, 'verified')
  assert.deepEqual(flow.calls, ['eligibility', 'verify-kai'])
  assert.equal(flow.receipt(), null)
})

test('eligibility and password verification never submit deletion or persist a ticket', async () => {
  const flow = fixture()
  await flow.controller.submit()
  await flow.controller.verify('test-password')
  assert.deepEqual(flow.calls, [])
  await flow.controller.checkEligibility()
  await flow.controller.verify('test-password')
  assert.equal(flow.state.stage, 'verified')
  assert.deepEqual(flow.calls, ['eligibility', 'verify'])
  assert.equal(flow.receipt(), null)
})

test('explicit submission persists only the capability before the request and signs out after acceptance', async () => {
  const flow = fixture()
  await flow.controller.checkEligibility()
  await flow.controller.verify('test-password')
  await flow.controller.submit()
  assert.deepEqual(flow.calls, ['eligibility', 'verify', 'save', 'submit', 'logout'])
  assert.equal(flow.state.stage, 'processing')
  assert.deepEqual(flow.receipt(), { ticket: 'deletion-only-test-capability', expiresAt: now + DELETION_RECEIPT_TTL_MS })
})

test('timeout stays uncertain and retries status with the SAME ticket without another submit', async () => {
  const flow = fixture()
  await flow.controller.checkEligibility()
  await flow.controller.verify('test-password')
  flow.fail()
  await assert.rejects(flow.controller.submit(), /timeout/)
  assert.equal(flow.state.stage, 'uncertain')
  assert.ok(flow.receipt())
  assert.ok(!flow.calls.includes('logout'))
  await flow.controller.submit()
  await flow.controller.checkStatus()
  assert.equal(flow.calls.filter(value => value === 'submit').length, 1)
  assert.equal(flow.calls.filter(value => value === 'status').length, 1)
  assert.equal(flow.state.stage, 'processing')
})

test('server blockers do not sign out, discard entitlements, or claim completion', async () => {
  const flow = fixture()
  await flow.controller.checkEligibility()
  await flow.controller.verify('test-password')
  flow.result({ status: 'blocked', blockers: [{ code: 'active_service', message: 'Resolve active service first', count: 2 }], completed_at: null })
  await flow.controller.submit()
  assert.equal(flow.state.stage, 'blocked')
  assert.equal(flow.state.blockers[0].count, 2)
  assert.ok(!flow.calls.includes('logout'))
  assert.ok(flow.receipt())
})

test('completion requires backend completed and clears the persisted capability', async () => {
  const flow = fixture()
  flow.controller.restore({ ticket: 'deletion-only-test-capability', expiresAt: now + 600_000 })
  assert.equal(flow.state.stage, 'uncertain')
  assert.deepEqual(flow.calls, [])
  flow.result({ status: 'completed', blockers: [], completed_at: '2026-09-04T10:00:01Z' })
  await flow.controller.checkStatus()
  assert.equal(flow.state.stage, 'completed')
  assert.equal(flow.state.completedAt, '2026-09-04T10:00:01Z')
  assert.equal(flow.state.ticket, '')
  assert.equal(flow.receipt(), null)
  assert.deepEqual(flow.calls, ['status', 'logout', 'clear-receipt'])
})

test('restoring a receipt never replays deletion; explicit verified retry uses the same ticket', async () => {
  const flow = fixture()
  flow.controller.restore({ ticket: 'deletion-only-test-capability', expiresAt: now + 600_000 })
  flow.result({ status: 'verified', blockers: [], completed_at: null })
  await flow.controller.checkStatus()
  assert.deepEqual(flow.calls, ['status'])
  await flow.controller.submit()
  assert.deepEqual(flow.calls, ['status', 'submit'])
})

test('duplicate taps while a submit is pending send exactly one request', async () => {
  const flow = fixture()
  await flow.controller.checkEligibility()
  await flow.controller.verify('test-password')
  let release = () => {}
  flow.hold(new Promise(resolve => { release = resolve }))
  const pending = flow.controller.submit()
  await flow.controller.submit()
  assert.equal(flow.calls.filter(value => value === 'submit').length, 1)
  release()
  await pending
})

test('receipt rejects expired, malformed or excessive retention and never preserves unrelated data', () => {
  assert.equal(validDeletionReceipt({ ticket: 'x', expiresAt: now }, now), null)
  assert.equal(validDeletionReceipt({ ticket: 'x', expiresAt: now + DELETION_RECEIPT_TTL_MS + 1 }, now), null)
  assert.equal(validDeletionReceipt({ ticket: '', expiresAt: now + 1000 }, now), null)
  assert.equal(validDeletionReceipt({ ticket: 'x', expiresAt: Infinity }, now), null)
  assert.deepEqual(validDeletionReceipt({ ticket: 'x', expiresAt: now + 1000, password: 'never-retain' }, now), { ticket: 'x', expiresAt: now + 1000 })
  assert.deepEqual(validDeletionReceipt({ ticket: 'x', expiresAt: now + 1000, ownerUserId: 12 }, now), { ticket: 'x', expiresAt: now + 1000, ownerUserId: 12 })
})

test('receipt owner isolates cleanup from other logged-in accounts and old ownerless receipts', async () => {
  const state = createDeletionState()
  const clearedOwners: Array<number | undefined> = []
  const controller = createDeletionController({
    state, now: () => now, ownerUserId: () => 17,
    eligibility: async () => ({ eligible: true, blockers: [], automatic_actions: [], verification_methods: ['password'] }),
    verify: async () => ({ ticket: 'owner-scoped-capability', expires_at: new Date(now + 1000).toISOString() }),
    submit: async () => ({ status: 'processing', blockers: [], completed_at: null }),
    status: async () => ({ status: 'completed', blockers: [], completed_at: '2026-09-04T10:00:01Z' }),
    saveReceipt: (receipt) => { assert.equal(receipt.ownerUserId, 17) }, clearReceipt: () => {},
    clearSession: (owner) => { clearedOwners.push(owner) },
  })
  await controller.checkEligibility()
  await controller.verify('test-password')
  await controller.submit()
  assert.deepEqual(clearedOwners, [17])
  controller.restore({ ticket: 'owner-scoped-capability', expiresAt: now + 1000, ownerUserId: 17 })
  await controller.checkStatus()
  assert.deepEqual(clearedOwners, [17, 17])
  controller.restore({ ticket: 'old-receipt', expiresAt: now + 1000 })
  await controller.checkStatus()
  assert.equal(clearedOwners[2], undefined)
  const page = readFileSync(new URL('../src/pages/account-deletion/index.vue', import.meta.url), 'utf8')
  assert.match(page, /if \(!ownerUserId \|\| userStore.userInfo\?\.id !== ownerUserId\) return\s+needsPageReset = true\s+userStore.logout/)
})

test('a delayed completion cannot clear a different account deletion receipt', () => {
  const source = readFileSync(new URL('../src/utils/account-deletion-receipt.ts', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText
  let stored: unknown = { ticket: 'account-B-receipt', expiresAt: Date.now() + 1000, ownerUserId: 22 }
  const exports: Record<string, any> = {}
  new Function('require', 'exports', 'uni', compiled)(() => ({ DELETION_RECEIPT_KEY: 'test-receipt', validDeletionReceipt }), exports, {
    getStorageSync: () => stored,
    setStorageSync: (_key: string, value: unknown) => { stored = value },
    removeStorageSync: () => { stored = null },
  })
  exports.clearDeletionReceipt('account-A-receipt')
  assert.ok(stored)
  exports.clearDeletionReceipt('account-B-receipt')
  assert.equal(stored, null)
  exports.rememberDeletionCompletion({ status: 'processing', blockers: [], completed_at: null })
  assert.equal(exports.consumeDeletionCompletion(), null)
  exports.rememberDeletionCompletion({ status: 'completed', blockers: [], completed_at: '2026-09-04T10:00:01Z' })
  assert.deepEqual(exports.consumeDeletionCompletion(), { status: 'completed', completed_at: '2026-09-04T10:00:01Z' })
  assert.equal(exports.consumeDeletionCompletion(), null)
})

test('deletion endpoints use the canonical client and submit/status do not attach session auth', () => {
  const api = readFileSync(new URL('../src/api/account-deletion.ts', import.meta.url), 'utf8')
  const request = readFileSync(new URL('../src/api/request.ts', import.meta.url), 'utf8')
  assert.match(api, /import \{ request \} from '@\/api\/request'/)
  assert.match(api, /url: '\/user\/account-deletion\/eligibility'/)
  assert.match(api, /url: '\/user\/account-deletion\/verify'/)
  assert.match(api, /url: '\/user\/account-deletion\/kai\/start'/)
  assert.match(api, /url: '\/user\/account-deletion\/kai\/verify'/)
  assert.match(api, /\/submit', method: 'POST', data: \{ ticket, confirm: true \}, auth: 'none'/)
  assert.match(api, /\/status', method: 'POST', data: \{ ticket \}, auth: 'none'/)
  assert.match(request, /options.auth === 'none' \? '' : getToken\(\)/)
  assert.match(request, /if \(options.auth === 'none' \|\| options.unauthorized === 'reject'\) \{\s+reject\(new ApiRequestError[\s\S]+?return\s+\}\s+expireSession/)
})

test('expired deletion capability rejects inline without bearer auth, session clearing or login redirect', async () => {
  const source = readFileSync(new URL('../src/api/request.ts', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText
  let cleared = 0
  let redirects = 0
  let staged = 0
  const headers: Array<Record<string, string>> = []
  const exports: Record<string, any> = {}
  const requireMock = (name: string) => {
    if (name === '@/utils/auth') return { getToken: () => 'ordinary-session-token', clearAuth: () => { cleared += 1 } }
    if (name === '@/utils/privacy-consent') return { requirePrivacyConsent: () => {} }
    if (name === '@/utils/auth-return-path') return { stageAuthReturnPath: () => { staged += 1 } }
    if (name === '@/utils/config') return { API_BASE: 'https://example.invalid/api' }
    if (name === '@/store/i18n') return { useI18nStore: () => ({ lang: 'zh', t: (key: string) => key, tr: (value: string) => value }) }
    throw new Error(`Unexpected dependency: ${name}`)
  }
  new Function('require', 'exports', 'uni', compiled)(requireMock, exports, {
    request: (options: any) => { headers.push(options.header); options.success({ statusCode: 401, data: { code: 401, msg: 'Capability expired' } }) },
    reLaunch: () => { redirects += 1 }, $emit: () => {}, showToast: () => {},
  })
  await assert.rejects(exports.request({ url: '/user/account-deletion/status', auth: 'none', silent: true }), (error: any) => error.statusCode === 401)
  assert.equal(headers[0].Authorization, undefined)
  assert.equal(cleared, 0)
  assert.equal(redirects, 0)
  assert.equal(staged, 0)
  // Default behavior remains exactly the existing session-auth flow.
  await assert.rejects(exports.request({ url: '/user/profile' }))
  assert.equal(headers[1].Authorization, 'Bearer ordinary-session-token')
  assert.equal(cleared, 1)
  assert.equal(redirects, 1)
  assert.equal(staged, 1)
})

test('late blockers during processing stay visible without being treated as completion', async () => {
  const flow = fixture()
  flow.controller.restore({ ticket: 'deletion-only-test-capability', expiresAt: now + 1000 })
  flow.result({ status: 'processing', blockers: [{ code: 'pending_settlement', message: 'Settlement needs attention', count: 1 }], completed_at: null })
  await flow.controller.checkStatus()
  assert.equal(flow.state.stage, 'processing')
  assert.equal(flow.state.blockers[0].code, 'pending_settlement')
  assert.equal(flow.state.completedAt, null)
  assert.ok(!flow.calls.includes('clear-receipt'))
})

test('mobile entry, consent, password wiping and bounded status recovery are present', () => {
  const page = readFileSync(new URL('../src/pages/account-deletion/index.vue', import.meta.url), 'utf8')
  const settings = readFileSync(new URL('../src/pages/settings/index.vue', import.meta.url), 'utf8')
  const login = readFileSync(new URL('../src/pages/login/index.vue', import.meta.url), 'utf8')
  const pages = JSON.parse(readFileSync(new URL('../src/pages.json', import.meta.url), 'utf8'))
  assert.match(settings, /nav\('\/pages\/account-deletion\/index'\)/)
  assert.ok(pages.pages.some((item: { path: string }) => item.path === 'pages/account-deletion/index'))
  assert.match(page, /acknowledged = ref\(false\)/)
  assert.match(page, /@confirm="confirmDeletion"/)
  assert.match(page, /finally \{ password.value = '' \}/)
  assert.match(page, /polls >= 6/)
  assert.match(page, /if \(receipt\) \{ controller.restore\(receipt\); void checkStatus\(\) \}/)
  assert.match(page, /controller\.verifyKai\(callback\.token\)/)
  assert.match(page, /acknowledged\.value = false/)
  assert.match(login, /v-if="pendingDeletion"/)
  assert.doesNotMatch(page, /clearStorage|setStorageSync\([^)]*password|console\./)
})

test('deletion stays scoped while the privacy policy publishes the approved contact', () => {
  const page = readFileSync(new URL('../src/pages/account-deletion/index.vue', import.meta.url), 'utf8')
  const privacy = readFileSync(new URL('../src/pages/agreement/index.vue', import.meta.url), 'utf8')
  const legalDocuments = readFileSync(new URL('../src/config/legal-documents.ts', import.meta.url), 'utf8')
  assert.match(page, /<scroll-view scroll-y class="body">\s+<view v-if="receiptView"/)
  assert.doesNotMatch(page, /\/pages\/kefu\/index|deletionResolveHelp/)
  assert.doesNotMatch(page, /callContactPhone|platformContactNumber|platformContactLink|deletion-contact|4001082026/)
  assert.match(privacy, /v-for="paragraph in section.paragraphs"/)
  assert.match(legalDocuments, /LEGAL_CONTACT_PHONE = '\+86 4001082026'/)
  assert.match(legalDocuments, /联系我们：\$\{LEGAL_CONTACT_PHONE\}/)
})

test('the relocated shared contact helper still requires explicit activation with the exact international number', () => {
  const source = readFileSync(new URL('../src/utils/contact-phone.ts', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText
  const called: string[] = []
  const exports: Record<string, any> = {}
  new Function('exports', 'uni', compiled)(exports, {
    makePhoneCall: (options: { phoneNumber: string }) => { called.push(options.phoneNumber) },
  })
  assert.deepEqual(called, [])
  exports.callContactPhone()
  assert.deepEqual(called, ['+864001082026'])
})
