import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const readSource = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('iOS binds or replaces an email through canonical authenticated APIs', () => {
  const api = readSource('../src/api/user.ts')
  const page = readSource('../src/pages/recovery-email/index.vue')
  const settings = readSource('../src/pages/settings/index.vue')
  const pages = JSON.parse(readSource('../src/pages.json'))

  assert.match(api, /url: '\/user\/recovery-email'/)
  assert.match(api, /url: '\/user\/recovery-email\/request-verification'/)
  assert.match(api, /url: '\/auth\/recovery\/config'[\s\S]*?auth: 'none'[\s\S]*?silent: true/)
  assert.match(api, /data: \{ email, current_password: currentPassword \}/)
  assert.match(page, /getRecoveryEmailStatus/)
  assert.match(page, /requestRecoveryEmailVerification\(email, form\.currentPassword\)/)
  assert.match(page, /status\?\.verified/)
  assert.match(page, /result\.already_verified/)
  assert.match(page, /emailEnabled\.value !== true/)
  assert.match(page, /generation !== loadGeneration/)
  assert.match(page, /onHide\(\(\) => \{[\s\S]*?active = false[\s\S]*?loadGeneration \+= 1/)
  assert.match(page, /if \(!active \|\| generation !== submitGeneration\) return/)
  assert.match(settings, /nav\('\/pages\/recovery-email\/index'\)/)
  assert.ok(pages.pages.some((item: { path: string }) => item.path === 'pages/recovery-email/index'))
})

test('email-binding form keeps credentials transient and explains verification', () => {
  const page = readSource('../src/pages/recovery-email/index.vue')
  const locale = readSource('../src/store/i18n.ts')

  assert.match(page, /finally \{\s+if \(generation === submitGeneration\) \{\s+form\.currentPassword = ''/)
  assert.match(page, /onHide\(\(\) => \{[\s\S]*?form\.email = ''\s+form\.currentPassword = ''/)
  assert.match(page, /onUnmounted\(\(\) => \{[\s\S]*?form\.email = ''\s+form\.currentPassword = ''/)
  assert.doesNotMatch(page, /setStorageSync|getStorageSync|console\./)
  assert.match(locale, /recoveryEmail: '绑定邮箱'/)
  assert.match(locale, /recoveryEmail: 'Email binding'/)
  assert.match(locale, /recoveryEmailBound: '已绑定邮箱'/)
  assert.match(locale, /recoveryEmailUnbound: '未绑定邮箱'/)
  assert.match(locale, /recoveryEmailSentHint: '请前往新邮箱点击邮件中的链接完成验证。验证完成前，当前绑定邮箱不会改变。'/)
  assert.match(locale, /recoveryEmailSentHint: 'Open the link in the new email to finish verification\. Your current bound email remains unchanged until then\.'/)
  assert.equal((locale.match(/recoveryEmailPrivacyHint: /g) || []).length, 2)
  for (const message of [
    '当前密码错误',
    '邮箱找回服务尚未配置',
    '邮箱服务尚未配置',
    '找回请求参数无效，请检查后重试',
    '请求过于频繁，请稍后再试',
  ]) assert.match(locale, new RegExp(`'${message}':`))
})

test('settings ignores stale email-status responses and distinguishes read failures from unbound state', () => {
  const settings = readSource('../src/pages/settings/index.vue')
  const locale = readSource('../src/store/i18n.ts')

  assert.match(settings, /const sessionToken = userStore\.token/)
  assert.match(settings, /const sessionUserId = userStore\.userInfo\?\.id \?\? null/)
  assert.match(settings, /generation === recoveryEmailGeneration/)
  assert.match(settings, /userStore\.token === sessionToken/)
  assert.match(settings, /sessionUserId === null \|\| \(userStore\.userInfo\?\.id \?\? null\) === sessionUserId/)
  assert.match(settings, /if \(!isCurrentRequest\(\)\) return\s+recoveryEmail\.value = nextStatus/)
  assert.match(settings, /catch \{\s+if \(!isCurrentRequest\(\)\) return\s+recoveryEmail\.value = null\s+recoveryEmailLoadFailed\.value = true/)
  assert.match(settings, /onHide\(deactivateRecoveryEmail\)/)
  assert.match(settings, /function deactivateRecoveryEmail\(\) \{[\s\S]*?recoveryEmailActive = false[\s\S]*?recoveryEmailGeneration \+= 1/)
  assert.match(settings, /uni\.\$on\('wod-session-changed', onSessionChanged\)/)
  assert.match(settings, /recoveryEmailLoadFailed\.value\s+\? 'recoveryEmailLoadFailed'/)
  assert.match(settings, /if \(recoveryEmailLoadFailed\.value\) return 'recoveryEmailStatusUnavailable'/)
  assert.match(locale, /recoveryEmailStatusUnavailable: '状态暂不可用'/)
  assert.match(locale, /recoveryEmailStatusUnavailable: 'Status unavailable'/)
})
