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
