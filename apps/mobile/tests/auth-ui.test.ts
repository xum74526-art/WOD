import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'


const loginSource = readFileSync(new URL('../src/pages/login/index.vue', import.meta.url), 'utf8')
const apiSource = readFileSync(new URL('../src/api/user.ts', import.meta.url), 'utf8')


test('mobile login and registration accept one email-or-phone identifier', () => {
  assert.match(loginSource, /authMethod === 'password'/)
  assert.match(loginSource, /v-model="form\.identifier" type="text"/)
  assert.match(loginSource, /userStore\.login\(form\.identifier\.trim\(\), form\.password\)/)
  assert.match(loginSource, /userStore\.register\(form\.username, form\.identifier\.trim\(\), form\.password\)/)
  assert.doesNotMatch(loginSource, /v-model="form\.phone" type="number"/)
})


test('mobile exposes Kai authentication and exchanges its one-time ticket for a canonical bearer session', () => {
  assert.match(loginSource, /setAuthMethod\('kai'\)/)
  assert.match(apiSource, /url: '\/auth\/kai\/start'/)
  assert.match(apiSource, /url: '\/auth\/kai\/exchange'/)
  assert.match(apiSource, /exchangeKaiTicket[\s\S]*?\.then\(toMobileSession\)/)
})
