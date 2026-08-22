import assert from 'node:assert/strict'
import test from 'node:test'

import { normalizeNativeApiBase, PRODUCTION_API_BASE } from '../src/utils/api-base.ts'

test('native app defaults to the canonical cloud API', () => {
  assert.equal(normalizeNativeApiBase(), PRODUCTION_API_BASE)
  assert.equal(normalizeNativeApiBase('https://wod.kai.com/api/'), PRODUCTION_API_BASE)
})

test('native app refuses unsafe or ambiguous API endpoints', () => {
  for (const value of [
    'http://wod.kai.com/api',
    'https://wod.kai.com',
    'https://wod.kai.com/api/v1',
    'https://user:secret@wod.kai.com/api',
    'https://wod.kai.com/api?debug=1',
  ]) {
    assert.throws(() => normalizeNativeApiBase(value))
  }
})
