import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const manifest = JSON.parse(readFileSync(new URL('../src/manifest.json', import.meta.url), 'utf8'))
const privacy = manifest['app-plus']?.distribute?.ios?.privacyDescription ?? {}

test('iOS declares purpose strings for each user-selected media source', () => {
  for (const key of [
    'NSPhotoLibraryUsageDescription',
    'NSCameraUsageDescription',
    'NSMicrophoneUsageDescription',
  ]) {
    assert.equal(typeof privacy[key], 'string')
    assert.ok(privacy[key].trim().length >= 12, `${key} must explain the user-facing purpose`)
  }
  assert.equal(privacy.NSPhotoLibraryAddUsageDescription, undefined)
})

test('media permissions correspond to features that are actually reachable', () => {
  const sources = [
    '../src/pages/profile-edit/index.vue',
    '../src/pages/verification/index.vue',
    '../src/pages/community/publish.vue',
  ].map(relative => readFileSync(new URL(relative, import.meta.url), 'utf8')).join('\n')

  assert.match(sources, /uni\.chooseImage\(/)
  assert.match(sources, /uni\.chooseVideo\(/)
})
