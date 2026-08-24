import assert from 'node:assert/strict'
import test from 'node:test'

import { normalizeNativeApiBase, PRODUCTION_API_BASE } from '../src/utils/api-base.ts'

test('native app defaults to the canonical cloud API', () => {
  assert.equal(normalizeNativeApiBase(), PRODUCTION_API_BASE)
  assert.equal(normalizeNativeApiBase('https://wod.kai.com/api/'), PRODUCTION_API_BASE)
  assert.equal(normalizeNativeApiBase('https://WOD.KAI.COM:443/api'), PRODUCTION_API_BASE)
})

test('native API validation does not require the browser URL global', () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'URL')
  Object.defineProperty(globalThis, 'URL', { configurable: true, value: undefined })
  try {
    assert.equal(normalizeNativeApiBase(), PRODUCTION_API_BASE)
  } finally {
    if (descriptor) Object.defineProperty(globalThis, 'URL', descriptor)
    else delete (globalThis as { URL?: unknown }).URL
  }
})

test('native app refuses unsafe or ambiguous API endpoints', () => {
  for (const value of [
    'http://wod.kai.com/api',
    'https://wod.kai.com',
    'https://wod.kai.com/api/v1',
    'https://user:secret@wod.kai.com/api',
    'https://wod.kai.com/api?debug=1',
    'https://wod.kai.com:70000/api',
  ]) {
    assert.throws(() => normalizeNativeApiBase(value))
  }
})
