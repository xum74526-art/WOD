import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const readSource = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('password login opens the native account-recovery flow without a browser handoff', () => {
  const page = readSource('../src/pages/login/index.vue')
  const pages = JSON.parse(readSource('../src/pages.json'))

  assert.match(page, /<view v-if="mode === 'login'" class="account-recovery-row">/)
  assert.equal((page.match(/@tap="openAccountRecovery"/g) || []).length, 1)
  assert.match(page, /uni\.navigateTo\(\{ url: '\/pages\/forgot-password\/index' \}\)/)
  assert.doesNotMatch(page, /resolvePublicWebUrl|openExternalLink/)
  assert.ok(pages.pages.some((item: { path: string }) => item.path === 'pages/forgot-password/index'))
  assert.ok(pages.pages.some((item: { path: string }) => item.path === 'pages/reset-password/index'))

  const recoveryHandler = page.match(/function openAccountRecovery\(\) \{([\s\S]*?)\n\}/)?.[1] || ''
  assert.doesNotMatch(recoveryHandler, /openExternalLink|resolvePublicWebUrl|setStorageSync|setStorage|token|sms/i)
})

test('account-recovery entry has matching Chinese and English copy', () => {
  const locale = readSource('../src/store/i18n.ts')
  assert.equal((locale.match(/forgotPassword: /g) || []).length, 2)
  assert.equal((locale.match(/passwordRecoveryTitle: /g) || []).length, 2)
  assert.match(locale, /forgotPassword: '忘记密码？'/)
  assert.match(locale, /forgotPassword: 'Forgot password\?'/)
})
