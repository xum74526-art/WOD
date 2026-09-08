import assert from 'node:assert/strict'
import test from 'node:test'
import {
  parsePasswordResetUrl,
  passwordResetCallbackFingerprint,
  stagePasswordResetCallback,
  takePendingPasswordResetToken,
} from '../src/utils/password-reset-callback.ts'

test('parses verified WOD reset links with fragment tokens', () => {
  assert.deepEqual(parsePasswordResetUrl('https://wod.kai.com/reset-password#token=secret%2Bvalue'), {
    token: 'secret+value',
  })
})

test('supports trusted universal links and origin-stripped iOS arguments', () => {
  assert.deepEqual(parsePasswordResetUrl('https://wod.kai.com/reset-password#token=web-token'), { token: 'web-token' })
  assert.deepEqual(parsePasswordResetUrl('reset-password#token=runtime-token'), { token: 'runtime-token' })
})

test('rejects tokens from untrusted links and invalid callbacks', () => {
  assert.equal(parsePasswordResetUrl('https://example.com/reset-password#token=secret'), null)
  assert.equal(parsePasswordResetUrl('kai://other#token=secret'), null)
  assert.equal(parsePasswordResetUrl('kai://reset-password#token=secret'), null)
  assert.equal(parsePasswordResetUrl('#token=secret'), null)
  assert.equal(parsePasswordResetUrl('https://wod.kai.com/reset-password?token=secret'), null)
  assert.equal(parsePasswordResetUrl('reset-password?token=secret'), null)
  assert.equal(parsePasswordResetUrl('https://wod.kai.com/reset-password#token='), null)
})

test('keeps a staged token only in memory and consumes it once', () => {
  const link = 'https://wod.kai.com/reset-password#token=one-time-token'
  assert.equal(stagePasswordResetCallback(link), true)
  assert.equal(takePendingPasswordResetToken(), 'one-time-token')
  assert.equal(takePendingPasswordResetToken(), '')
  assert.equal(stagePasswordResetCallback(link), false)
  assert.equal(stagePasswordResetCallback(link, true), true)
  assert.equal(takePendingPasswordResetToken(), 'one-time-token')
})

test('fingerprints callbacks without revealing the reset token', () => {
  const fingerprint = passwordResetCallbackFingerprint({ token: 'sensitive-reset-token' })
  assert.match(fingerprint, /^[0-9a-f]+$/)
  assert.ok(!fingerprint.includes('sensitive-reset-token'))
})
