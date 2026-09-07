import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const readSource = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('recovery email API uses the canonical authenticated request wrapper and payload', async () => {
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

test('settings opens an in-app recovery email page that shows status and verifies changes', () => {
  const settings = readSource('../src/pages/settings/index.vue')
  const page = readSource('../src/pages/recovery-email/index.vue')
  const pages = JSON.parse(readSource('../src/pages.json'))

  assert.match(settings, /nav\('\/pages\/recovery-email\/index'\)/)
  assert.ok(pages.pages.some((item: { path: string }) => item.path === 'pages/recovery-email/index'))
  assert.match(page, /getRecoveryEmailStatus\(true\)/)
  assert.match(page, /getAccountRecoveryConfig\(\)/)
  assert.match(page, /requestRecoveryEmailVerification\(normalizedEmail, submittedPassword\)/)
  assert.match(page, /status\?\.verified && status\.email/)
  assert.match(page, /password\s+:maxlength="64"/)
  assert.match(page, /recoveryEmailSentMessage/)
  assert.match(page, /onHide\(leavePage\)/)
  assert.match(page, /onUnload\(leavePage\)/)
  assert.match(page, /pageGeneration \+= 1[\s\S]*?clearSensitiveFields\(\)/)
  assert.match(page, /config\?\.email_enabled === false/)
  assert.match(page, /emailServiceEnabled/)
  assert.match(page, /v-else-if="configFailed"[\s\S]*?@tap="reloadPage"[\s\S]*?recoveryEmailRetry/)
  for (const message of ['当前密码错误', '邮箱找回服务尚未配置', '邮箱服务尚未配置', '找回请求参数无效，请检查后重试', '请求过于频繁，请稍后再试']) {
    assert.match(page, new RegExp(message))
  }
  assert.doesNotMatch(page, /setStorageSync|getStorageSync|resolvePublicWebUrl|openExternalLink|sms/i)
})

test('recovery email screen has matching Chinese and English copy', () => {
  const locale = readSource('../src/store/i18n.ts')
  for (const key of [
    'recoveryEmailTitle',
    'recoveryEmailVerified',
    'recoveryEmailNotBound',
    'recoveryEmailCurrentPassword',
    'recoveryEmailSentMessage',
  ]) {
    assert.equal((locale.match(new RegExp(`${key}:`, 'g')) || []).length, 2, `${key} must exist in both dictionaries`)
  }
  assert.match(locale, /recoveryEmailTitle: '绑定邮箱'/)
  assert.match(locale, /recoveryEmailTitle: 'Bind email'/)
  assert.match(locale, /recoveryEmailVerified: '已绑定邮箱'/)
  assert.match(locale, /recoveryEmailNotBound: '未绑定邮箱'/)
  assert.doesNotMatch(locale, /recoveryEmail(?:Title|MenuHint|StatusTitle|StatusLoading|NotBoundHint|LoadFailed|BindTitle|ChangeTitle|FormHint|Address|AddressPlaceholder|VerificationNotice|AlreadyVerifiedMessage): '[^']*找回邮箱/)
})
