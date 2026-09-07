import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const readSource = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('password login exposes one Web account-recovery entry without native token handling', () => {
  const page = readSource('../src/pages/login/index.vue')

  assert.match(page, /<view v-if="mode === 'login'" class="account-recovery-row">/)
  assert.equal((page.match(/@tap="openAccountRecovery"/g) || []).length, 1)
  assert.match(page, /import \{ resolvePublicWebUrl \} from '@\/utils\/config'/)
  assert.match(page, /import \{ openExternalLink \} from '@\/utils\/external-link'/)
  assert.match(page, /openExternalLink\(\s*resolvePublicWebUrl\('\/forgot-password'\)/)

  const recoveryHandler = page.match(/function openAccountRecovery\(\) \{([\s\S]*?)\n\}/)?.[1] || ''
  assert.doesNotMatch(recoveryHandler, /setStorageSync|setStorage|token|sms/i)
})

test('account-recovery entry has matching Chinese and English copy', () => {
  const locale = readSource('../src/store/i18n.ts')
  assert.equal((locale.match(/forgotPassword: /g) || []).length, 2)
  assert.equal((locale.match(/accountRecoveryLinkCopied: /g) || []).length, 2)
  assert.match(locale, /forgotPassword: '忘记密码？'/)
  assert.match(locale, /forgotPassword: 'Forgot password\?'/)
})
