import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const readSource = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('recovery email API is owned by the canonical account-recovery module', async () => {
  const source = readSource('../src/api/account-recovery.ts')
  const userApi = readSource('../src/api/user.ts')
  assert.match(source, /import \{ request \} from '\.\/request'/)
  assert.doesNotMatch(source, /uni\.request|fetch\(|axios|API_BASE/)
  assert.doesNotMatch(userApi, /getRecoveryEmailStatus|requestRecoveryEmailVerification|interface RecoveryEmailStatus/)

  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText
  const calls: Array<Record<string, unknown>> = []
  const exports: Record<string, any> = {}
  new Function('require', 'exports', compiled)(
    (name: string) => {
      assert.equal(name, './request')
      return { request: async (options: Record<string, unknown>) => { calls.push(options); return { accepted: true, already_verified: false } } }
    },
    exports,
  )

  await exports.getRecoveryEmailStatus()
  await exports.getAccountRecoveryConfig()
  await exports.requestRecoveryEmailVerification('owner@example.com', 'current-password')
  assert.deepEqual(calls, [
    { url: '/user/recovery-email', silent: true },
    { url: '/auth/recovery/config', auth: 'none', silent: true },
    {
      url: '/user/recovery-email/request-verification',
      method: 'POST',
      data: { email: 'owner@example.com', current_password: 'current-password' },
      silent: true,
    },
  ])
})

test('binding page separates status and capability failures without presenting failure as unbound', () => {
  const page = readSource('../src/pages/recovery-email/index.vue')

  assert.match(page, /const \[emailStatus, recoveryConfig\] = await Promise\.allSettled/)
  assert.match(page, /emailStatus\.status === 'fulfilled'[\s\S]*?else \{\s+status\.value = null\s+loadFailed\.value = true/)
  assert.match(page, /recoveryConfig\.status === 'fulfilled'[\s\S]*?else \{\s+config\.value = null\s+configFailed\.value = true/)
  assert.match(page, /v-else-if="!loading && !loadFailed" class="status-badge"/)
  assert.match(page, /<template v-else-if="loadFailed">[\s\S]*?recoveryEmailLoadFailed[\s\S]*?<text v-else-if="status\?\.verified && status\.email"/)
  assert.match(page, /v-else-if="configFailed"[\s\S]*?@tap="reloadPage"[\s\S]*?recoveryEmailRetry/)
  assert.match(page, /v-if="requestError" class="request-error" role="alert"/)
  assert.doesNotMatch(page, /setStorageSync|getStorageSync|resolvePublicWebUrl|openExternalLink|sms/i)
})

test('binding page clears credentials and cancels late responses on hide or unload', () => {
  const page = readSource('../src/pages/recovery-email/index.vue')

  assert.match(page, /const submittedPassword = currentPassword\.value\s+currentPassword\.value = ''\s+requestError\.value = ''\s+submitting\.value = true[\s\S]*?requestRecoveryEmailVerification\(normalizedEmail, submittedPassword\)/)
  assert.match(page, /if \(!active \|\| generation !== pageGeneration\) return/)
  assert.match(page, /if \(active && generation === pageGeneration\) requestError\.value = requestErrorMessage\(cause\)/)
  assert.match(page, /function leavePage\(\) \{[\s\S]*?active = false[\s\S]*?pageGeneration \+= 1[\s\S]*?requestError\.value = ''[\s\S]*?clearSensitiveFields\(\)/)
  assert.match(page, /function clearSensitiveFields\(\) \{\s+email\.value = ''\s+currentPassword\.value = ''/)
  assert.match(page, /onHide\(leavePage\)/)
  assert.match(page, /onUnload\(leavePage\)/)
  assert.match(page, /recoveryEmailPrivacyHint/)
})

test('settings rejects stale email status after account changes and distinguishes read failure', () => {
  const settings = readSource('../src/pages/settings/index.vue')
  const pages = JSON.parse(readSource('../src/pages.json'))

  assert.match(settings, /getRecoveryEmailStatus, type RecoveryEmailStatus \} from '@\/api\/account-recovery'/)
  assert.match(settings, /const sessionToken = userStore\.token/)
  assert.match(settings, /const sessionUserId = userStore\.userInfo\?\.id \?\? null/)
  assert.match(settings, /generation === recoveryEmailGeneration/)
  assert.match(settings, /userStore\.token === sessionToken/)
  assert.match(settings, /sessionUserId === null \|\| \(userStore\.userInfo\?\.id \?\? null\) === sessionUserId/)
  assert.match(settings, /if \(!isCurrentRequest\(\)\) return\s+recoveryEmail\.value = nextStatus/)
  assert.match(settings, /catch \{\s+if \(!isCurrentRequest\(\)\) return\s+recoveryEmail\.value = null\s+recoveryEmailLoadFailed\.value = true/)
  assert.match(settings, /if \(recoveryEmailLoadFailed\.value\) return 'recoveryEmailStatusUnavailable'/)
  assert.match(settings, /recoveryEmail\.value\?\.verified \? 'recoveryEmailVerified' : 'recoveryEmailNotBound'/)
  assert.match(settings, /onHide\(deactivateRecoveryEmail\)/)
  assert.match(settings, /function deactivateRecoveryEmail\(\) \{[\s\S]*?recoveryEmailActive = false[\s\S]*?recoveryEmailGeneration \+= 1/)
  assert.match(settings, /function onSessionChanged\(\) \{[\s\S]*?recoveryEmailGeneration \+= 1[\s\S]*?recoveryEmail\.value = null[\s\S]*?refreshRecoveryEmail\(\)/)
  assert.match(settings, /uni\.\$on\('wod-session-changed', onSessionChanged\)/)
  assert.match(settings, /nav\('\/pages\/recovery-email\/index'\)/)
  assert.ok(pages.pages.some((item: { path: string }) => item.path === 'pages/recovery-email/index'))
})

test('binding page has matching Chinese and English semantic copy', () => {
  const locale = readSource('../src/store/i18n.ts')
  for (const key of [
    'recoveryEmailTitle',
    'recoveryEmailVerified',
    'recoveryEmailVerifiedHint',
    'recoveryEmailNotBound',
    'recoveryEmailStatusUnavailable',
    'recoveryEmailCurrentPassword',
    'recoveryEmailPrivacyHint',
    'recoveryEmailSentMessage',
  ]) {
    assert.equal((locale.match(new RegExp(`${key}:`, 'g')) || []).length, 2, `${key} must exist in both dictionaries`)
  }
  assert.match(locale, /recoveryEmailTitle: '绑定邮箱'/)
  assert.match(locale, /recoveryEmailTitle: 'Bind email'/)
  assert.match(locale, /recoveryEmailStatusUnavailable: '状态暂不可用'/)
  assert.match(locale, /recoveryEmailStatusUnavailable: 'Status unavailable'/)
})
