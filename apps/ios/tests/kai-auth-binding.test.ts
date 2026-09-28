import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { basename } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const appName = basename(fileURLToPath(new URL('..', import.meta.url)))
const platformSource = readFileSync(new URL('../src/utils/client-platform.ts', import.meta.url), 'utf8')
const apiSource = readFileSync(new URL('../src/api/user.ts', import.meta.url), 'utf8')
const settingsSource = readFileSync(new URL('../src/pages/settings/index.vue', import.meta.url), 'utf8')
const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
const loginSource = readFileSync(new URL('../src/pages/login/index.vue', import.meta.url), 'utf8')

test('authentication requests identify the native client platform', () => {
  assert.ok(appName === 'android' || appName === 'ios')
  assert.match(platformSource, new RegExp(`CLIENT_PLATFORM = '${appName}'`))
  assert.match(apiSource, /auth\/login[\s\S]*?client_id: CLIENT_PLATFORM/)
  assert.match(apiSource, /auth\/register[\s\S]*?client_id: CLIENT_PLATFORM/)
  assert.match(apiSource, /auth\/kai\/start[\s\S]*?client_id: CLIENT_PLATFORM/)
  assert.match(apiSource, /auth\/kai\/start[\s\S]*?terms_accepted: true/)
  assert.match(apiSource, /intent === 'register'[\s\S]*?invite_code:/)
})

test('signed-in users explicitly bind Kai identity without replacing their session', () => {
  assert.match(apiSource, /url: '\/auth\/kai\/status'/)
  assert.match(apiSource, /url: '\/auth\/kai\/bind\/start'/)
  assert.match(apiSource, /url: '\/auth\/kai\/bind\/exchange'/)
  assert.match(settingsSource, /startKaiBinding\(\)/)
  assert.match(settingsSource, /kaiIdentityBindingConfirm/)
  assert.match(appSource, /callback\.bindTicket/)
  assert.match(appSource, /user\.bindKaiIdentity\(callback\.bindTicket\)/)
  assert.match(loginSource, /<view class="method-switch"[^>]*>/)
  assert.match(loginSource, /startKaiAuth\(mode\.value, mode\.value === 'register' \? form\.invite_code : ''\)/)
  assert.match(loginSource, /options\?\.invite_code/)
  assert.match(loginSource, /PENDING_KAI_INTENT_KEY/)
  assert.doesNotMatch(loginSource, /identity_not_bound/)
  assert.doesNotMatch(loginSource, /if \(value === 'register'\) authMethod\.value = 'phone'/)
  assert.doesNotMatch(loginSource, /closedTestPhoneNotice/)
  assert.match(loginSource, /kaiIdentityHint/)
})
