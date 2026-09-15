import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

import { normalizeBuyRequestContactPhone } from '../src/utils/buy-request-contact.ts'

test('buy-request contact phone matches the API storage contract', () => {
  assert.equal(normalizeBuyRequestContactPhone(' +86 (139) 1000-0001 '), '+8613910000001')
  assert.equal(normalizeBuyRequestContactPhone('1'.repeat(20)), '1'.repeat(20))
  assert.equal(normalizeBuyRequestContactPhone(`+${'1'.repeat(15)}`), `+${'1'.repeat(15)}`)
  assert.equal(normalizeBuyRequestContactPhone('12345'), null)
  assert.equal(normalizeBuyRequestContactPhone('86+13910000001'), null)
  assert.equal(normalizeBuyRequestContactPhone('+0123456789'), null)
  assert.equal(normalizeBuyRequestContactPhone('139.1000.0001'), null)
  assert.equal(normalizeBuyRequestContactPhone(`+${'1'.repeat(20)}`), null)
  assert.equal(normalizeBuyRequestContactPhone(`+${'1'.repeat(16)}`), null)
  assert.equal(normalizeBuyRequestContactPhone('1'.repeat(21)), null)
})

test('buy-request form validates and caps contact phone before submitting', () => {
  const page = fs.readFileSync(new URL('../src/pages/buy-request/index.vue', import.meta.url), 'utf8')
  assert.match(page, /type="tel" maxlength="32"/)
  assert.match(page, /normalizeBuyRequestContactPhone\(form\.phone\)/)
  assert.match(page, /t\('enterValidContactPhone'\)/)
})
