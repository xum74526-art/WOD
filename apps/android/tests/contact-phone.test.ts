import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const readSource = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')

const contactButton = '<button class="contact-link" @tap="callContactPhone">{{ t(\'platformContactLink\', { phone: t(\'platformContactNumber\') }) }}</button>'

test('login and registration share one labeled contact action inside the auth card', () => {
  const page = readSource('../src/pages/login/index.vue')
  assert.match(page, /mode = ref<'login' \| 'register'>\('login'\)/)
  assert.match(page, /@tap="setMode\('login'\)"/)
  assert.match(page, /@tap="setMode\('register'\)"/)
  assert.match(page, /import \{ callContactPhone \} from '@\/utils\/contact-phone'/)
  assert.equal((page.match(/@tap="callContactPhone"/g) || []).length, 1)
  const [before, after] = page.split(contactButton)
  assert.match(before, /<text v-if="authMethod === 'kai'" class="security-note">[^\n]+<\/text>\s*$/)
  assert.match(after, /^\s+<\/view>\s+<\/view>\s+<\/view>\s+<\/template>/)
  // Contact must not submit authentication or bypass consent.
  assert.match(page, /if \(!agree.value\) \{ uni.showToast/)
  assert.match(page, /if \(userStore.isLogin\) \{\s+setTimeout\(enterAuthenticatedApp, 800\)/)
})

test('settings has one labeled contact row before deletion and logout controls', () => {
  const page = readSource('../src/pages/settings/index.vue')
  assert.match(page, /import \{ callContactPhone \} from '@\/utils\/contact-phone'/)
  assert.equal((page.match(/@tap="callContactPhone"/g) || []).length, 1)
  assert.match(page, /<view class="menu-item contact-link" role="button" @tap="callContactPhone">\s+<text class="mi-text">\{\{ t\('platformContactLink', \{ phone: t\('platformContactNumber'\) \}\) \}\}<\/text>/)
  assert.ok(page.indexOf('class="menu-item contact-link"') < page.indexOf("nav('/pages/account-deletion/index')"))
  assert.ok(page.indexOf('class="menu-item contact-link"') < page.indexOf('@tap="showLogout = true"'))
  assert.doesNotMatch(page, /class="contact-phone"/)
  assert.match(page, /nav\('\/pages\/account-deletion\/index'\)/)
  assert.match(page, /@confirm="onLogout"/)
  assert.match(page, /function onLogout\(\) \{\s+showLogout.value = false\s+void userStore.signOut\(\)\s+uni.reLaunch\(\{ url: '\/pages\/login\/index' \}\)/)
})

test('only login and settings pages contain platform contact entries', () => {
  const pagesRoot = new URL('../src/pages/', import.meta.url)
  function phonePages(directory: URL, prefix = ''): string[] {
    return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
      const relative = prefix + entry.name
      if (entry.isDirectory()) return phonePages(new URL(entry.name + '/', directory), relative + '/')
      if (!entry.name.endsWith('.vue')) return []
      const source = readFileSync(new URL(entry.name, directory), 'utf8')
      return /callContactPhone|platformContactLink|platformContactNumber|4001082026/.test(source) ? [relative] : []
    })
  }
  assert.deepEqual(phonePages(pagesRoot).sort(), ['login/index.vue', 'settings/index.vue'])
})

test('removing the home phone preserves the existing authentication and loading boundaries', () => {
  const page = readSource('../src/pages/index/index.vue')
  assert.doesNotMatch(page, /callContactPhone|platformContactNumber|contact-phone|4001082026/)
  assert.match(page, /class="hero"/)
  assert.match(page, /v-if="homeLoadError"/)
  assert.match(page, /if \(!userStore\.isLogin\) \{ uni\.reLaunch\(\{ url: '\/pages\/login\/index' \}\); return \}/)
  assert.match(page, /Promise\.all\(\[load\(\), loadHotMarket\(false\)\]\)/)
})

test('removing the support phone preserves session loading, errors and message entry', () => {
  const page = readSource('../src/pages/kefu/index.vue')
  assert.doesNotMatch(page, /callContactPhone|platformContactNumber|contact-phone|4001082026/)
  assert.match(page, /<AppNavBar :title="t\('onlineService'\)" \/>\s+<view class="service-banner">/)
  assert.match(page, /v-if="initialLoading"/)
  assert.match(page, /v-else-if="loadError"/)
  assert.match(page, /onMounted\(loadSession\)/)
  assert.match(page, /const session = await getSupportSession\(supportApiLanguage\(i18n\.lang\)\)/)
  assert.match(page, /class="input-bar"/)
})

test('contact translations render the approved number with the requested contact label', () => {
  const locale = readSource('../src/store/i18n.ts')
  assert.equal((locale.match(/platformContactNumber: '\+86 4001082026'/g) || []).length, 2)
  const labels = [...locale.matchAll(/platformContactLink: '([^']+)'/g)].map(match => match[1])
  assert.deepEqual(labels.map(label => label.replace('{phone}', '+86 4001082026')), [
    '联系我们：+86 4001082026', 'Contact us: +86 4001082026',
  ])
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
