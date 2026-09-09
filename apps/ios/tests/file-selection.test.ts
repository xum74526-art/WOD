import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { normalizeTempFilePaths } from '../src/utils/file-selection.ts'

test('native image selection normalizes both a single path and a path array', () => {
  assert.deepEqual(normalizeTempFilePaths('file:///one.jpg'), ['file:///one.jpg'])
  assert.deepEqual(normalizeTempFilePaths(['file:///one.jpg', 'file:///two.jpg']), ['file:///one.jpg', 'file:///two.jpg'])
  assert.deepEqual(normalizeTempFilePaths([null, '', 'file:///one.jpg']), ['file:///one.jpg'])
  assert.deepEqual(normalizeTempFilePaths(undefined), [])
})

test('all iOS image pickers use the shared path normalizer', () => {
  for (const page of [
    '../src/pages/community/publish.vue',
    '../src/pages/profile-edit/index.vue',
    '../src/pages/verification/index.vue',
  ]) {
    const source = readFileSync(new URL(page, import.meta.url), 'utf8')
    assert.match(source, /normalizeTempFilePaths\(res\.tempFilePaths\)/)
    assert.doesNotMatch(source, /res\.tempFilePaths\[0\]|res\.tempFilePaths as string\[\]/)
  }
})
