import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

import {
  acceptPrivacyConsent,
  clearPrivacyConsent,
  HONG_KONG_PROCESSING_CONSENT_VERSION,
  hasCurrentPrivacyConsent,
  isCurrentPrivacyConsentReceipt,
  PRIVACY_CONSENT_STORAGE_KEY,
  PRIVACY_CONSENT_SCHEMA_VERSION,
  type PrivacyConsentStorage,
} from '../src/utils/privacy-consent.ts'
import { LEGAL_VERSION } from '../src/config/legal-documents.ts'

class MemoryStorage implements PrivacyConsentStorage {
  value: unknown = ''
  getStorageSync(key: string) {
    assert.equal(key, PRIVACY_CONSENT_STORAGE_KEY)
    return this.value
  }
  setStorageSync(key: string, value: unknown) {
    assert.equal(key, PRIVACY_CONSENT_STORAGE_KEY)
    this.value = value
  }
  removeStorageSync(key: string) {
    assert.equal(key, PRIVACY_CONSENT_STORAGE_KEY)
    this.value = ''
  }
}

const baseInput = {
  language: 'zh-Hans' as const,
  platform: 'ios' as const,
  regionScope: 'mainland-china' as const,
  agreementAndPrivacyAccepted: true,
  hongKongProcessingAccepted: true,
}

test('Hong Kong processing consent is recorded separately with the current legal version and region', () => {
  const storage = new MemoryStorage()
  const receipt = acceptPrivacyConsent(baseInput, storage, 1_800_000_000_000)

  assert.equal(receipt.legalVersion, LEGAL_VERSION)
  assert.equal(receipt.schemaVersion, PRIVACY_CONSENT_SCHEMA_VERSION)
  assert.equal(receipt.regionScope, 'mainland-china')
  assert.equal(receipt.hongKongProcessingAccepted, true)
  assert.equal(receipt.hongKongProcessingConsentVersion, HONG_KONG_PROCESSING_CONSENT_VERSION)
  assert.equal(receipt.acceptedAt, 1_800_000_000_000)
  assert.equal(hasCurrentPrivacyConsent(storage), true)
})

test('the gate rejects missing general consent or missing Hong Kong processing consent for every region', () => {
  const storage = new MemoryStorage()
  assert.throws(
    () => acceptPrivacyConsent({ ...baseInput, agreementAndPrivacyAccepted: false }, storage),
    /User Agreement and Privacy Policy/,
  )
  assert.throws(
    () => acceptPrivacyConsent({ ...baseInput, hongKongProcessingAccepted: false }, storage),
    /Separate consent/,
  )
  assert.throws(
    () => acceptPrivacyConsent({
      ...baseInput,
      regionScope: 'other',
      hongKongProcessingAccepted: false,
    }, storage),
    /Separate consent/,
  )
  assert.equal(hasCurrentPrivacyConsent(storage), false)
})

test('non-mainland users record their region and the same explicit Hong Kong processing confirmation', () => {
  const storage = new MemoryStorage()
  const receipt = acceptPrivacyConsent({
    ...baseInput,
    platform: 'ios',
    regionScope: 'other',
    hongKongProcessingAccepted: true,
  }, storage, 1_800_000_000_001)

  assert.equal(receipt.regionScope, 'other')
  assert.equal(receipt.hongKongProcessingAccepted, true)
  assert.equal(receipt.hongKongProcessingConsentVersion, HONG_KONG_PROCESSING_CONSENT_VERSION)
  assert.equal(isCurrentPrivacyConsentReceipt(receipt), true)
})

test('old, malformed, or unreadable receipts fail closed', () => {
  const storage = new MemoryStorage()
  const current = acceptPrivacyConsent(baseInput, storage, 1_800_000_000_002)
  storage.value = { ...current, legalVersion: '0.9' }
  assert.equal(hasCurrentPrivacyConsent(storage), false)
  storage.value = { ...current, hongKongProcessingConsentVersion: '0.9' }
  assert.equal(hasCurrentPrivacyConsent(storage), false)
  storage.value = { ...current, hongKongProcessingAccepted: false }
  assert.equal(hasCurrentPrivacyConsent(storage), false)
  storage.value = {
    ...current,
    schemaVersion: PRIVACY_CONSENT_SCHEMA_VERSION - 1,
    mainlandChinaCrossBorderAccepted: true,
    crossBorderConsentVersion: '1.0',
  }
  assert.equal(hasCurrentPrivacyConsent(storage), false)
  storage.value = { ...current, acceptedAt: 0 }
  assert.equal(hasCurrentPrivacyConsent(storage), false)
  assert.equal(hasCurrentPrivacyConsent({
    getStorageSync() { throw new Error('storage unavailable') },
    setStorageSync() {},
  }), false)
})

test('withdrawal invalidates the receipt before cleanup and reports storage failure', () => {
  const storage = new MemoryStorage()
  acceptPrivacyConsent(baseInput, storage, 1_800_000_000_003)
  assert.equal(clearPrivacyConsent(storage), true)
  assert.equal(hasCurrentPrivacyConsent(storage), false)

  const current = acceptPrivacyConsent(baseInput, new MemoryStorage(), 1_800_000_000_004)
  const failedStorage: PrivacyConsentStorage = {
    getStorageSync: () => current,
    setStorageSync: () => { throw new Error('storage unavailable') },
    removeStorageSync: () => { throw new Error('storage unavailable') },
  }
  assert.equal(clearPrivacyConsent(failedStorage), false)
  assert.equal(hasCurrentPrivacyConsent(failedStorage), true)

  const invalidatedStorage: PrivacyConsentStorage = {
    value: current,
    getStorageSync() { return this.value },
    setStorageSync(_key, value) { this.value = value },
    removeStorageSync() { throw new Error('cleanup unavailable') },
  } as PrivacyConsentStorage & { value: unknown }
  assert.equal(clearPrivacyConsent(invalidatedStorage), true)
  assert.equal(hasCurrentPrivacyConsent(invalidatedStorage), false)
})

test('privacy consent is the first local page and every transport fails closed', () => {
  const pages = JSON.parse(readFileSync(new URL('../src/pages.json', import.meta.url), 'utf8'))
  const requestSource = readFileSync(new URL('../src/api/request.ts', import.meta.url), 'utf8')
  const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const navSource = readFileSync(new URL('../src/utils/nav.ts', import.meta.url), 'utf8')
  const pageSource = readFileSync(new URL('../src/pages/privacy-consent/index.vue', import.meta.url), 'utf8')
  const settingsSource = readFileSync(new URL('../src/pages/settings/index.vue', import.meta.url), 'utf8')

  assert.equal(pages.pages[0]?.path, 'pages/privacy-consent/index')
  for (const functionName of ['requestTrustedPublicJson', 'request', 'upload', 'download']) {
    const start = requestSource.indexOf(`export function ${functionName}`)
    const next = requestSource.indexOf('\nexport function ', start + 1)
    const source = requestSource.slice(start, next < 0 ? requestSource.length : next)
    assert.ok(start >= 0, `${functionName} must exist`)
    assert.match(source, /requirePrivacyConsent\(\)/)
    assert.ok(source.indexOf('requirePrivacyConsent()') < source.search(/uni\.(request|uploadFile|downloadFile)/))
  }

  const runtimeStart = appSource.indexOf('function startNetworkedRuntime()')
  const launchStart = appSource.indexOf('onLaunch(() =>')
  const runtimeSource = appSource.slice(runtimeStart, launchStart)
  assert.match(runtimeSource, /!hasCurrentPrivacyConsent\(\)/)
  assert.match(runtimeSource, /user\.restore\(\)/)
  assert.match(runtimeSource, /checkForAppUpdate/)
  assert.match(runtimeSource, /useCommerceStore\(\)\.refresh/)
  assert.match(runtimeSource, /useNotificationStore\(\)\.startPolling/)
  assert.match(runtimeSource, /probeKaiBindingCallback/)
  assert.doesNotMatch(appSource.slice(launchStart), /user\.restore\(\)/)

  assert.match(pageSource, /acceptPrivacyConsent/)
  assert.match(pageSource, /regionScope === 'mainland-china'/)
  assert.match(pageSource, /hongKongProcessingAccepted/)
  assert.doesNotMatch(pageSource, /v-if="regionScope === 'mainland-china'" class="cross-border-box"/)
  assert.match(pageSource, /pages\/agreement\/index\?type=/)
  assert.doesNotMatch(pageSource, /在任何联网请求|Before any network request/)
  assert.match(navSource, /if \(!hasCurrentPrivacyConsent\(\)\)/)
  assert.match(navSource, /uni\.reLaunch\(\{ url: '\/pages\/privacy-consent\/index' \}\)/)
  assert.match(appSource, /function stopNetworkedRuntime\(\)/)
  assert.match(appSource, /PRIVACY_CONSENT_REVOKED_EVENT, handlePrivacyConsentRevoked/)
  assert.match(appSource, /useNotificationStore\(\)\.reset\(\)/)
  assert.match(settingsSource, /clearPrivacyConsent/)
  assert.match(settingsSource, /withdrawPrivacyConsentDescription/)
  assert.match(settingsSource, /uni\.\$emit\(PRIVACY_CONSENT_REVOKED_EVENT\)/)
})

test('no request, upload, or download starts when the consent guard rejects', async () => {
  const source = readFileSync(new URL('../src/api/request.ts', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText
  const exports: Record<string, any> = {}
  let networkCalls = 0
  const requireMock = (name: string) => {
    if (name === '@/utils/privacy-consent') {
      return { requirePrivacyConsent: () => { throw new Error('consent-required') } }
    }
    if (name === '@/utils/auth') return { getToken: () => '', clearAuth: () => {} }
    if (name === '@/utils/auth-return-path') return { stageAuthReturnPath: () => {} }
    if (name === '@/utils/config') return { API_BASE: 'https://example.invalid/api' }
    if (name === '@/store/i18n') return { useI18nStore: () => { throw new Error('i18n should not initialize') } }
    throw new Error(`Unexpected dependency: ${name}`)
  }
  const transport = {
    request: () => { networkCalls += 1 },
    uploadFile: () => { networkCalls += 1 },
    downloadFile: () => { networkCalls += 1 },
  }
  new Function('require', 'exports', 'uni', compiled)(requireMock, exports, transport)

  await assert.rejects(exports.requestTrustedPublicJson({ url: 'https://api.bilibili.com/x/web-interface/view' }), /consent-required/)
  await assert.rejects(exports.request({ url: '/platform/capabilities' }), /consent-required/)
  await assert.rejects(exports.upload({ url: '/community/media' }), /consent-required/)
  await assert.rejects(exports.download({ url: '/user/avatar' }), /consent-required/)
  assert.equal(networkCalls, 0)
})

test('withdrawal prevents an automatic request retry from becoming a new network request', async () => {
  const source = readFileSync(new URL('../src/api/request.ts', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText
  const exports: Record<string, any> = {}
  let networkCalls = 0
  const requireMock = (name: string) => {
    if (name === '@/utils/privacy-consent') {
      return {
        requirePrivacyConsent: () => {
          if (networkCalls > 0) throw new Error('consent-withdrawn')
        },
      }
    }
    if (name === '@/utils/auth') return { getToken: () => '', clearAuth: () => {} }
    if (name === '@/utils/auth-return-path') return { stageAuthReturnPath: () => {} }
    if (name === '@/utils/config') return { API_BASE: 'https://example.invalid/api' }
    if (name === '@/store/i18n') {
      return { useI18nStore: () => ({ locale: 'en', t: (key: string) => key, tr: (value: string) => value }) }
    }
    throw new Error(`Unexpected dependency: ${name}`)
  }
  new Function('require', 'exports', 'uni', compiled)(requireMock, exports, {
    request: (options: { success(response: unknown): void }) => {
      networkCalls += 1
      options.success({ statusCode: 503, data: { code: 503, msg: 'retry' } })
    },
  })

  await assert.rejects(
    exports.request({ url: '/orders', retryUncertainOnce: true }),
    /consent-withdrawn/,
  )
  assert.equal(networkCalls, 1)
})

test('a response arriving after withdrawal cannot expire the session or navigate away from consent', async () => {
  const source = readFileSync(new URL('../src/api/request.ts', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText
  const exports: Record<string, any> = {}
  let consentGranted = true
  let success: ((response: unknown) => void) | null = null
  let clearAuthCalls = 0
  let relaunchCalls = 0
  const requireMock = (name: string) => {
    if (name === '@/utils/privacy-consent') {
      return {
        requirePrivacyConsent: () => {
          if (!consentGranted) throw new Error('consent-withdrawn')
        },
      }
    }
    if (name === '@/utils/auth') {
      return {
        getToken: () => 'existing-session',
        clearAuth: () => { clearAuthCalls += 1 },
      }
    }
    if (name === '@/utils/auth-return-path') return { stageAuthReturnPath: () => {} }
    if (name === '@/utils/config') return { API_BASE: 'https://example.invalid/api' }
    if (name === '@/store/i18n') {
      return { useI18nStore: () => ({ locale: 'en', t: (key: string) => key, tr: (value: string) => value }) }
    }
    throw new Error(`Unexpected dependency: ${name}`)
  }
  new Function('require', 'exports', 'uni', compiled)(requireMock, exports, {
    request: (options: { success(response: unknown): void }) => { success = options.success },
    reLaunch: () => { relaunchCalls += 1 },
    $emit: () => {},
    showToast: () => {},
  })

  const pending = exports.request({ url: '/user/profile' })
  assert.ok(success)
  consentGranted = false
  success!({ statusCode: 401, data: { code: 401, msg: 'expired' } })
  await assert.rejects(pending, /consent-withdrawn/)
  assert.equal(clearAuthCalls, 0)
  assert.equal(relaunchCalls, 0)
})

test('a failed back navigation cannot bypass the consent page', () => {
  const source = readFileSync(new URL('../src/utils/nav.ts', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText
  const exports: Record<string, any> = {}
  const relaunched: string[] = []
  const tabs: string[] = []
  new Function('require', 'exports', 'uni', compiled)(
    (name: string) => {
      if (name === './privacy-consent') return { hasCurrentPrivacyConsent: () => false }
      if (name === './motion') {
        return {
          APP_MOTION: { routeIn: 240, routeOut: 220, tab: 180, micro: 160, sheet: 260, reduced: 80, lock: 420 },
          navigateAnimation: () => ({ animationType: 'pop-in', animationDuration: 240 }),
          backAnimation: () => ({ animationType: 'pop-out', animationDuration: 220 }),
        }
      }
      throw new Error(`Unexpected dependency: ${name}`)
    },
    exports,
    {
      navigateBack: (options: { fail(): void }) => options.fail(),
      reLaunch: ({ url }: { url: string }) => relaunched.push(url),
      switchTab: ({ url }: { url: string }) => tabs.push(url),
    },
  )

  exports.navigateBack()
  assert.deepEqual(relaunched, ['/pages/privacy-consent/index'])
  assert.deepEqual(tabs, [])
})
