import test from 'node:test'
import assert from 'node:assert/strict'

import {
  ensureClientRequestIntent,
  readClientRequestIntent,
} from '../src/utils/financial-request-intent.ts'

test('financial request intent survives an uncertain retry with the same input', () => {
  const first = ensureClientRequestIntent(null, '100.00|alipay', 'recharge-1000000000-abcd1234')
  const retry = ensureClientRequestIntent(first, '100.00|alipay', 'recharge-2000000000-efgh5678')
  assert.equal(retry.requestId, first.requestId)
})

test('financial request intent rotates when material input changes', () => {
  const first = ensureClientRequestIntent(null, '10.000000|7', 'withdraw-1000000000-abcd1234')
  const changed = ensureClientRequestIntent(first, '20.000000|7', 'withdraw-2000000000-efgh5678')
  assert.notEqual(changed.requestId, first.requestId)
  assert.equal(readClientRequestIntent({ version: 1, requestId: 'short', fingerprint: 'x' }), null)
})
