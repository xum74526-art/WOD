import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const readSource = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('only the shared login/register screen and settings provide a labeled contact action', () => {
  const login = readSource('../src/pages/login/index.vue')
  const settings = readSource('../src/pages/settings/index.vue')
  const home = readSource('../src/pages/index/index.vue')
  const support = readSource('../src/pages/kefu/index.vue')
  const deletion = readSource('../src/pages/account-deletion/index.vue')
  const agreement = readSource('../src/pages/agreement/index.vue')

  for (const page of [login, settings]) {
    assert.match(page, /t\('platformContactLink', \{ phone: t\('platformContactNumber'\) \}\)/)
    assert.match(page, /@tap="callContactPhone"/)
    assert.match(page, /import \{ callContactPhone \} from '@\/utils\/contact-phone'/)
  }
  for (const page of [home, support, deletion, agreement]) {
    assert.doesNotMatch(page, /callContactPhone|platformContactNumber|platformContactLink|4001082026/)
  }
})

test('all supported languages use the approved number and an explicit contact label', () => {
  const locale = readSource('../src/store/i18n.ts')
  assert.equal((locale.match(/platformContactNumber: '\+86 4001082026'/g) || []).length, 2)
  assert.match(locale, /platformContactLink: '联系我们：\{phone\}'/)
  assert.match(locale, /platformContactLink: 'Contact us: \{phone\}'/)
})

test('the shared contact helper only invokes the dialer after explicit activation', () => {
  const compiled = ts.transpileModule(readSource('../src/utils/contact-phone.ts'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText
  const called: string[] = []
  const exports: Record<string, any> = {}
  new Function('exports', 'uni', compiled)(exports, {
    makePhoneCall: (options: { phoneNumber: string }) => { called.push(options.phoneNumber) },
  })
  assert.deepEqual(called, [])
  exports.callContactPhone()
  assert.deepEqual(called, ['+864001082026'])
})
