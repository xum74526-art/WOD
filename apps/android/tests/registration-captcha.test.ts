import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const loginSource = readFileSync(new URL('../src/pages/login/index.vue', import.meta.url), 'utf8')

test('refreshing a registration captcha clears every stale captcha value first', () => {
  const handler = loginSource.match(/async function refreshCaptcha\(silent = false\) \{([\s\S]*?)\n\}/)?.[1] || ''
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
  assert.match(handler, /finally \{\s*captchaRefreshPromise = null\s*\}/)
})

test('a failed registration silently refreshes the consumed captcha without changing login failures', () => {
  const handler = loginSource.match(/async function submit\(\) \{([\s\S]*?)\n\}/)?.[1] || ''

  assert.match(handler, /const isRegistration = mode\.value === 'register'/)
  assert.match(handler, /!captchaKey\.value \|\| !form\.captcha_code/)
  assert.match(handler, /catch \{\s*if \(isRegistration\) await refreshCaptcha\(true\)\s*\}/)
  assert.equal((handler.match(/userStore\.register\(/g) || []).length, 1)
})
