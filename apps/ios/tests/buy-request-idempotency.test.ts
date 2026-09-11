import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

import { ensureClientRequestIntent } from '../src/utils/client-request-intent.ts'

test('buy-request retries reuse one client request id until the intent changes', () => {
  let sequence = 0
  const createRequestId = () => `buy-request-${++sequence}`
  const payload = { request_type: 'online', gpu_model: 'H100', quantity: 2, gpu_hours: 24 }

  const first = ensureClientRequestIntent(null, payload, createRequestId)
  const retry = ensureClientRequestIntent(first, { ...payload }, createRequestId)
  assert.equal(retry.requestId, first.requestId)
  assert.equal(sequence, 1)

  const changed = ensureClientRequestIntent(retry, { ...payload, gpu_hours: 48 }, createRequestId)
  assert.notEqual(changed.requestId, first.requestId)

  const afterCancel = ensureClientRequestIntent(null, payload, createRequestId)
  assert.notEqual(afterCancel.requestId, first.requestId)
  assert.equal(sequence, 3)
})

test('buy-request submission sends the stable id in the JSON body and clears it only after success or cancel', () => {
  const api = fs.readFileSync(new URL('../src/api/buy-request.ts', import.meta.url), 'utf8')
  const page = fs.readFileSync(new URL('../src/pages/buy-request/index.vue', import.meta.url), 'utf8')

  assert.match(api, /client_request_id\?: string/)
  assert.match(page, /if \(submitting\.value[^)]*\) return/)
  assert.match(page, /client_request_id: ensureRequestId\(payload\)/)
  assert.match(page, /await createBuyRequest[\s\S]*?resetRequestIntent\(\)/)
  assert.match(page, /function closeForm\(\) \{ resetRequestIntent\(\); showForm\.value = false \}/)
})
