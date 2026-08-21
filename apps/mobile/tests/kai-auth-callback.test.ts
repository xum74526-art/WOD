import assert from 'node:assert/strict'
import test from 'node:test'
import {
  kaiAuthCallbackFingerprint,
  parseKaiAuthQuery,
  parseKaiAuthUrl,
} from '../src/utils/kai-auth-callback.ts'

test('parses an iOS Kai ticket callback', () => {
  assert.deepEqual(parseKaiAuthUrl('kai://auth?kai_ticket=ticket%2Bvalue%2F123'), {
    ticket: 'ticket+value/123',
  })
})

test('parses a cancelled Kai callback', () => {
  assert.deepEqual(parseKaiAuthUrl('kai://auth?kai_error=access_denied'), {
    error: 'access_denied',
  })
})

test('ignores callbacks from untrusted schemes or paths', () => {
  assert.equal(parseKaiAuthUrl('https://example.com/?kai_ticket=secret'), null)
  assert.equal(parseKaiAuthUrl('kai://other?kai_ticket=secret'), null)
})

test('supports uni-app page query callbacks', () => {
  assert.deepEqual(parseKaiAuthQuery({ kai_ticket: 'page-ticket' }), { ticket: 'page-ticket' })
})

test('fingerprints callbacks without persisting the ticket itself', () => {
  const fingerprint = kaiAuthCallbackFingerprint({ ticket: 'one-time-ticket' })
  assert.match(fingerprint, /^[0-9a-f]+$/)
  assert.ok(!fingerprint.includes('one-time-ticket'))
})
