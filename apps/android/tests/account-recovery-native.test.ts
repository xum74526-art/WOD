import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const readSource = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('native password recovery uses the canonical request wrapper without authentication', async () => {
  const source = readSource('../src/api/account-recovery.ts')
  assert.match(source, /import \{ request \} from '\.\/request'/)
  assert.doesNotMatch(source, /uni\.request|fetch\(|axios|API_BASE/)

  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText
  const calls: Array<Record<string, unknown>> = []
  const exports: Record<string, any> = {}
  new Function('require', 'exports', compiled)(
    (name: string) => {
      if (name === './request') {
        return { request: async (options: Record<string, unknown>) => { calls.push(options); return { accepted: true } } }
      }
      if (name === './user') return { getAccountRecoveryConfig: async () => ({ email_enabled: true }) }
      throw new Error(`Unexpected module: ${name}`)
    },
    exports,
  )

  await exports.requestPasswordReset('owner@example.com')
  await exports.confirmPasswordReset('x'.repeat(43), 'Replacement-Password-84')
  assert.deepEqual(calls, [
    {
      url: '/auth/email/password-reset/request',
      method: 'POST',
      data: { email: 'owner@example.com' },
      auth: 'none',
      silent: true,
    },
    {
      url: '/auth/email/password-reset/confirm',
      method: 'POST',
      data: { token: 'x'.repeat(43), password: 'Replacement-Password-84' },
      auth: 'none',
      silent: true,
    },
  ])
})

test('forgot-password page stays in the app and preserves anti-enumeration messaging', () => {
  const page = readSource('../src/pages/forgot-password/index.vue')

  assert.match(page, /getAccountRecoveryConfig\(\)/)
  assert.match(page, /requestPasswordReset\(normalizedEmail\)/)
  assert.match(page, /uni\.navigateTo\(\{ url: '\/pages\/reset-password\/index' \}\)/)
  assert.match(page, /passwordRecoveryHaveCode/)
  assert.match(page, /passwordRecoveryPrivacyNotice/)
  assert.match(page, /passwordRecoveryEmailSentMessage/)
  assert.match(page, /EMAIL_PATTERN/)
  assert.match(page, /onHide\(leavePage\)/)
  assert.match(page, /onUnload\(leavePage\)/)
  assert.doesNotMatch(page, /openExternalLink|resolvePublicWebUrl|uni\.request|邮箱不存在|账号不存在|sms/i)
})

test('reset-password page consumes a one-shot in-memory token and clears sensitive fields', () => {
  const page = readSource('../src/pages/reset-password/index.vue')

  assert.match(page, /takePendingPasswordResetToken\(\)/)
  assert.match(page, /v-model="token"/)
  assert.match(page, /passwordResetCodePlaceholder/)
  assert.match(page, /const normalizedToken = computed\(\(\) => token\.value\.trim\(\)\)/)
  assert.match(page, /const submittedToken = normalizedToken\.value/)
  assert.match(page, /confirmPasswordReset\(submittedToken, submittedPassword\)/)
  assert.match(page, /candidate\.length >= 32 && candidate\.length <= 256/)
  assert.match(page, /password\.value\.length < 8 \|\| password\.value\.length > 64/)
  assert.match(page, /function clearSensitiveFields\(\) \{[\s\S]*?token\.value = ''[\s\S]*?password\.value = ''[\s\S]*?confirmation\.value = ''/)
  assert.match(page, /onLoad\(\(\) => \{[\s\S]*?takePendingToken\(\)/)
  assert.match(page, /onShow\(\(\) => \{[\s\S]*?takePendingToken\(\)/)
  assert.match(page, /uni\.\$on\('wod-password-reset-token-ready', takePendingToken\)/)
  assert.match(page, /uni\.\$off\('wod-password-reset-token-ready', takePendingToken\)/)
  assert.doesNotMatch(page, /onHide\(leavePage\)/)
  assert.match(page, /onUnload\(\(\) => \{[\s\S]*?leavePage\(\)/)
  assert.doesNotMatch(page, /setStorageSync|getStorageSync|removeStorageSync|openExternalLink|resolvePublicWebUrl|console\.|options\?\.token/i)
})

test('native recovery routes and bilingual copy are complete', () => {
  const pages = JSON.parse(readSource('../src/pages.json')) as { pages: Array<{ path: string }> }
  const locale = readSource('../src/store/i18n.ts')

  assert.ok(pages.pages.some(item => item.path === 'pages/forgot-password/index'))
  assert.ok(pages.pages.some(item => item.path === 'pages/reset-password/index'))
  for (const key of [
    'passwordRecoveryTitle',
    'passwordRecoveryPrivacyNotice',
    'passwordRecoveryEmailSentMessage',
    'passwordRecoveryHaveCode',
    'passwordResetTitle',
    'passwordResetCode',
    'passwordResetSecurityNotice',
    'passwordResetInvalidToken',
    'passwordResetSuccessMessage',
  ]) {
    assert.equal((locale.match(new RegExp(`${key}:`, 'g')) || []).length, 2, `${key} must exist in both dictionaries`)
  }
  assert.match(locale, /passwordRecoveryTitle: '找回密码'/)
  assert.match(locale, /passwordRecoveryTitle: 'Forgot password'/)
  assert.match(locale, /passwordRecoveryPrivacyNotice: '为保护账号，无论邮箱是否已绑定，提交后都会显示相同结果。'/)
  assert.match(locale, /passwordResetSecurityNotice: '重置码只能使用一次，并会在短时间内失效。KAI星算不会在设备中保存该重置码。'/)
})
