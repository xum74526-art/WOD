import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import {
  clearPendingLoginKaiCallback,
  createPendingKaiLoginIntent,
  hasPendingLoginKaiCallback,
  KAI_LOGIN_INTENT_TTL_MS,
  peekPendingLoginKaiCallback,
  readPendingKaiLoginIntent,
  stageLoginKaiCallback,
} from '../src/utils/login-kai-callback.ts'

test('requires a fresh local login intent before accepting a native callback', () => {
  const now = 2_000_000
  assert.equal(readPendingKaiLoginIntent(createPendingKaiLoginIntent('login', now), now), 'login')
  assert.equal(readPendingKaiLoginIntent(createPendingKaiLoginIntent('register', now), now), 'register')
  assert.equal(readPendingKaiLoginIntent({ intent: 'login', startedAt: now - KAI_LOGIN_INTENT_TTL_MS - 1 }, now), null)
  assert.equal(readPendingKaiLoginIntent({ intent: 'login', startedAt: now + 1 }, now), null)
  assert.equal(readPendingKaiLoginIntent('login', now), null)
})

test('stages a trusted cold-start login ticket in process memory', () => {
  clearPendingLoginKaiCallback()
  assert.equal(stageLoginKaiCallback('kai://auth?kai_ticket=cold-start%2Fticket', true), true)
  assert.deepEqual(peekPendingLoginKaiCallback(), { ticket: 'cold-start/ticket' })
  assert.equal(hasPendingLoginKaiCallback(), true)

  const source = readFileSync(new URL('../src/utils/login-kai-callback.ts', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /setStorageSync|localStorage|sessionStorage/)
})

test('rejects foreign callbacks and gates login errors on a pending intent', () => {
  clearPendingLoginKaiCallback()
  assert.equal(stageLoginKaiCallback('https://evil.example/?kai_ticket=stolen'), false)
  assert.equal(stageLoginKaiCallback('kai://other?kai_ticket=stolen'), false)
  assert.equal(stageLoginKaiCallback('kai://auth?kai_ticket=unsolicited'), false)
  assert.equal(stageLoginKaiCallback('kai://auth?kai_error=access_denied'), false)
  assert.equal(hasPendingLoginKaiCallback(), false)
  assert.equal(stageLoginKaiCallback('kai://auth?kai_error=access_denied', true), true)
  assert.deepEqual(peekPendingLoginKaiCallback(), { error: 'access_denied' })
})

test('supports argument-only newintent callbacks and never replaces a ticket with an error', () => {
  clearPendingLoginKaiCallback()
  assert.equal(stageLoginKaiCallback('?kai_ticket=newintent-ticket', true), true)
  assert.equal(stageLoginKaiCallback('kai_error=access_denied', true), false)
  assert.deepEqual(peekPendingLoginKaiCallback(), { ticket: 'newintent-ticket' })
  assert.equal(clearPendingLoginKaiCallback({ ticket: 'another-ticket' }), false)
  assert.equal(clearPendingLoginKaiCallback({ ticket: 'newintent-ticket' }), true)
  assert.equal(hasPendingLoginKaiCallback(), false)
})

test('cold-start routing waits for privacy consent and the login page owns consumption', () => {
  const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const consent = readFileSync(new URL('../src/pages/privacy-consent/index.vue', import.meta.url), 'utf8')
  const login = readFileSync(new URL('../src/pages/login/index.vue', import.meta.url), 'utf8')

  assert.match(app, /registerKaiBindingListener\(\)[\s\S]*captureLoginKaiCallback\(\)[\s\S]*PRIVACY_CONSENT_EVENT/)
  assert.match(app, /addEventListener\('newintent',[\s\S]*captureLoginKaiCallback\(\)[\s\S]*!hasCurrentPrivacyConsent\(\)/)
  assert.match(app, /!hasCurrentPrivacyConsent\(\) \|\| !hasPendingLoginKaiCallback\(\)/)
  assert.match(consent, /hasPendingLoginKaiCallback\(\)[\s\S]*reLaunch\(\{ url: '\/pages\/login\/index' \}\)/)
  assert.match(login, /peekPendingLoginKaiCallback\(\)[\s\S]*handleKaiCallback\(callback\)/)
  assert.match(login, /wod-kai-login-callback-ready/)
  assert.match(login, /clearPendingLoginKaiCallback\(callback\)/)
})
