import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const loginSource = readFileSync(new URL('../src/pages/login/index.vue', import.meta.url), 'utf8')
const localeSource = readFileSync(new URL('../src/store/i18n.ts', import.meta.url), 'utf8')

test('refreshing a registration captcha clears every stale captcha value first', () => {
  const handler = loginSource.match(/async function refreshCaptcha\(silent = false\): Promise<boolean> \{([\s\S]*?)\n\}/)?.[1] || ''
  const clearKey = handler.indexOf("captchaKey.value = ''")
  const clearImage = handler.indexOf("captchaImg.value = ''")
  const clearInput = handler.indexOf("form.captcha_code = ''")
  const requestCaptcha = handler.indexOf("url: '/auth/captcha'")

  assert.match(handler, /if \(captchaRefreshPromise\) return captchaRefreshPromise/)
  assert.ok(clearKey >= 0)
  assert.ok(clearImage > clearKey)
  assert.ok(clearInput > clearImage)
  assert.ok(requestCaptcha > clearInput)
  assert.match(handler, /url: '\/auth\/captcha', silent/)
  assert.match(handler, /captchaExpiresAt = Date\.now\(\) \+ CAPTCHA_FRESHNESS_MS/)
  assert.match(handler, /scheduleCaptchaExpiry\(\)\s*return true/)
  assert.match(handler, /catch \{[\s\S]*?return false/)
  assert.match(handler, /finally \{\s*captchaRefreshPromise = null\s*\}/)
})

test('a failed registration silently refreshes the consumed captcha without changing login failures', () => {
  const handler = loginSource.match(/async function submit\(\) \{([\s\S]*?)\n\}/)?.[1] || ''

  assert.match(handler, /const isRegistration = mode\.value === 'register'/)
  assert.match(handler, /if \(isRegistration && !hasFreshCaptcha\(\)\) \{[\s\S]*?await refreshCaptchaWithNotice\(true\)[\s\S]*?return/)
  assert.match(handler, /if \(isRegistration && !form\.captcha_code\)/)
  assert.match(handler, /catch \{\s*if \(isRegistration\) await refreshCaptcha\(true\)\s*\}/)
  assert.equal((handler.match(/userStore\.register\(/g) || []).length, 1)
})

test('captcha freshness follows the five-minute server lifetime with a safe client margin', () => {
  assert.match(loginSource, /const CAPTCHA_FRESHNESS_MS = 270_000/)
  assert.match(loginSource, /function hasFreshCaptcha\(now = Date\.now\(\)\) \{[\s\S]*?remaining > 0 && remaining <= CAPTCHA_FRESHNESS_MS/)
  assert.match(loginSource, /function scheduleCaptchaExpiry\(\) \{[\s\S]*?setTimeout\([\s\S]*?syncCaptchaLifecycle\(true\)/)
  assert.match(loginSource, /function syncCaptchaLifecycle[\s\S]*?form\.captcha_code[\s\S]*?refreshCaptchaWithNotice\(false\)/)
  assert.match(loginSource, /function refreshCaptchaWithNotice[\s\S]*?if \(captchaReplacementNoticePromise\) return captchaReplacementNoticePromise/)
  assert.match(loginSource, /function setMode[\s\S]*?syncCaptchaLifecycle\(false\)/)
  assert.match(loginSource, /function setAuthMethod[\s\S]*?syncCaptchaLifecycle\(false\)/)
  assert.match(loginSource, /callback\.error === 'identity_not_bound'[\s\S]*?syncCaptchaLifecycle\(true\)/)
  assert.match(loginSource, /onShow\(\(\) => \{[\s\S]*?syncCaptchaLifecycle\(true\)/)
  assert.match(loginSource, /onHide\(\(\) => \{[\s\S]*?stopCaptchaExpiryTimer\(\)/)
  assert.match(loginSource, /onUnmounted\(\(\) => \{[\s\S]*?stopCaptchaExpiryTimer\(\)/)
})

test('captcha replacement guidance is translated without claiming every refresh was an expiry', () => {
  assert.equal((localeSource.match(/registrationCaptchaRefreshed:/g) || []).length, 2)
  assert.equal((localeSource.match(/registrationCaptchaLoadFailed:/g) || []).length, 2)
  assert.match(localeSource, /registrationCaptchaRefreshed: '验证码已更新，请重新输入。'/)
  assert.match(localeSource, /registrationCaptchaRefreshed: 'The verification code was refreshed\. Please enter the new code\.'/)
})

test('registration fields enforce the canonical input lengths', () => {
  assert.match(loginSource, /v-model="form\.username"[^>]+maxlength="64"/)
  assert.match(loginSource, /v-model="form\.invite_code"[^>]+maxlength="16"/)
  assert.match(loginSource, /v-model="form\.password"[^>]+maxlength="64"/)
})

test('registration validates and normalizes fields before captcha and network work', () => {
  const handler = loginSource.match(/async function submit\(\) \{([\s\S]*?)\n\}/)?.[1] || ''
  const phoneGuard = handler.indexOf("t('请输入正确手机号')")
  const usernameGuard = handler.indexOf("t('registrationUsernameLength')")
  const passwordGuard = handler.indexOf("t('registrationPasswordLength')")
  const inviteGuard = handler.indexOf("t('registrationInviteCodeLength')")
  const captchaGuard = handler.indexOf('!hasFreshCaptcha()')
  const loginCall = handler.indexOf('userStore.login(')
  const registerCall = handler.indexOf('userStore.register(')

  assert.match(handler, /const normalizedPhone = form\.phone\.trim\(\)/)
  assert.match(handler, /const registrationUsername = form\.username\.trim\(\)/)
  assert.match(handler, /const registrationInviteCode = form\.invite_code\.trim\(\)\.toUpperCase\(\)/)
  assert.ok(phoneGuard >= 0)
  assert.ok(usernameGuard > phoneGuard)
  assert.ok(passwordGuard > usernameGuard)
  assert.ok(inviteGuard > passwordGuard)
  assert.ok(captchaGuard > inviteGuard)
  assert.ok(loginCall > phoneGuard)
  assert.ok(registerCall > captchaGuard)
  assert.match(handler, /\^1\\d\{10\}\$/)
  assert.match(handler, /registrationUsername\.length < 2 \|\| registrationUsername\.length > 64/)
  assert.match(handler, /form\.password\.length < 6 \|\| form\.password\.length > 64/)
  assert.match(handler, /registrationInviteCode\.length > 16/)
  assert.match(handler, /userStore\.login\(normalizedPhone, form\.password\)/)
  assert.match(handler, /userStore\.register\(registrationUsername, normalizedPhone, form\.password, registrationInviteCode \|\| undefined/)
})

test('phone validation guidance is localized for every supported language mode', () => {
  assert.match(loginSource, /t\('请输入正确手机号'\)/)
  assert.match(localeSource, /'请输入正确手机号': 'Enter a valid phone number'/)
})

test('registration length guidance is available in Chinese and English', () => {
  for (const key of ['registrationUsernameLength', 'registrationPasswordLength', 'registrationInviteCodeLength']) {
    assert.equal((localeSource.match(new RegExp(`${key}:`, 'g')) || []).length, 2)
  }
})

test('an invalid invite code has localized guidance', () => {
  assert.match(localeSource, /registrationInviteCodeInvalid: '邀请码无效，请检查后重试'/)
  assert.match(localeSource, /registrationInviteCodeInvalid: 'The invitation code is invalid\. Check it and try again\.'/)
})
