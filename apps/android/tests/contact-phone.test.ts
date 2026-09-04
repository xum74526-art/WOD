import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const readSource = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('home has one explicit pure-number contact entry before the existing asset and loading sections', () => {
  const page = readSource('../src/pages/index/index.vue')
  assert.match(page, /<button class="contact-phone" @tap="callContactPhone">\{\{ t\('platformContactNumber'\) \}\}<\/button>\s+<view class="hero">/)
  assert.equal((page.match(/@tap="callContactPhone"/g) || []).length, 1)
  assert.match(page, /import \{ callContactPhone \} from '@\/utils\/contact-phone'/)
  assert.ok(page.indexOf('class="contact-phone"') < page.indexOf('v-if="homeLoadError"'))
  // Adding the number must not change the existing home authentication boundary.
  assert.match(page, /if \(!userStore\.isLogin\) \{ uni\.reLaunch\(\{ url: '\/pages\/login\/index' \}\); return \}/)
  assert.match(page, /Promise\.all\(\[load\(\), loadHotMarket\(false\)\]\)/)
})

test('support has one explicit pure-number contact entry outside loading and error branches', () => {
  const page = readSource('../src/pages/kefu/index.vue')
  assert.match(page, /<AppNavBar :title="t\('onlineService'\)" \/>\s+<button class="contact-phone" @tap="callContactPhone">\{\{ t\('platformContactNumber'\) \}\}<\/button>\s+<view class="service-banner">/)
  assert.equal((page.match(/@tap="callContactPhone"/g) || []).length, 1)
  assert.match(page, /import \{ callContactPhone \} from '@\/utils\/contact-phone'/)
  assert.ok(page.indexOf('class="contact-phone"') < page.indexOf('v-if="initialLoading"'))
  assert.ok(page.indexOf('class="contact-phone"') < page.indexOf('v-else-if="loadError"'))
  // Preserve the existing authenticated support lifecycle and message entry.
  assert.match(page, /onMounted\(loadSession\)/)
  assert.match(page, /const session = await getSupportSession\(i18n\.lang\)/)
  assert.match(page, /class="input-bar"/)
})

test('all supported languages display exactly the approved number with no added label', () => {
  const locale = readSource('../src/store/i18n.ts')
  assert.equal((locale.match(/platformContactNumber: '\+86 4001082026'/g) || []).length, 2)
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
