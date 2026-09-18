import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const manifest = JSON.parse(readFileSync(new URL('../src/manifest.json', import.meta.url), 'utf8'))
const privacy = manifest['app-plus']?.distribute?.ios?.privacyDescription ?? {}
const safeArea = manifest['app-plus']?.safearea ?? {}
const themeSource = readFileSync(new URL('../src/store/theme.ts', import.meta.url), 'utf8')
const theme = JSON.parse(readFileSync(new URL('../src/theme.json', import.meta.url), 'utf8'))
const pages = JSON.parse(readFileSync(new URL('../src/pages.json', import.meta.url), 'utf8'))

test('iOS native chrome and the home-indicator safe area follow the in-app theme', () => {
  assert.deepEqual(manifest['app-plus']?.modules?.Invocation, {})
  assert.equal(safeArea.background, '#FFFFFF')
  assert.equal(safeArea.backgroundDark, '#0A0E14')
  assert.equal(safeArea.bottom?.offset, 'auto')
  assert.equal(manifest['app-plus']?.themeLocation, 'theme.json')
  assert.equal(theme.light.tabBackgroundColor, '#FFFFFF')
  assert.equal(theme.dark.tabBackgroundColor, '#0A0E14')
  assert.equal(pages.tabBar?.backgroundColor, '@tabBackgroundColor')
  assert.equal(pages.globalStyle?.backgroundColorBottom, '@backgroundColorContent')
  assert.match(themeSource, /plus\.nativeUI\.setUIStyle\(theme\)/)
  assert.match(themeSource, /setOverrideUserInterfaceStyle:/)
})

test('iOS declares purpose strings for each user-selected media source', () => {
  for (const key of [
    'NSPhotoLibraryUsageDescription',
    'NSCameraUsageDescription',
  ]) {
    assert.equal(typeof privacy[key], 'string')
    assert.ok(privacy[key].trim().length >= 12, `${key} must explain the user-facing purpose`)
  }
  assert.equal(privacy.NSPhotoLibraryAddUsageDescription, undefined)
  assert.equal(privacy.NSMicrophoneUsageDescription, undefined)
})

test('review build keeps only image permissions used by profile and identity flows', () => {
  const sources = [
    '../src/pages/profile-edit/index.vue',
    '../src/pages/verification/index.vue',
  ].map(relative => readFileSync(new URL(relative, import.meta.url), 'utf8')).join('\n')
  const communityPublisher = readFileSync(new URL('../src/pages/community/publish.vue', import.meta.url), 'utf8')

  assert.match(sources, /uni\.chooseImage\(/)
  assert.doesNotMatch(communityPublisher, /uni\.chooseImage|uni\.chooseVideo/)
})

test('localized iOS purpose strings match the review build feature set', () => {
  for (const locale of ['en', 'zh-Hans', 'zh-Hant']) {
    const strings = readFileSync(
      new URL(`../nativeResources/ios/Resources/${locale}.lproj/InfoPlist.strings`, import.meta.url),
      'utf8',
    )
    assert.match(strings, /"NSPhotoLibraryUsageDescription"\s*=/)
    assert.match(strings, /"NSCameraUsageDescription"\s*=/)
    assert.doesNotMatch(strings, /NSMicrophoneUsageDescription/)
    assert.doesNotMatch(strings, /community|社区|社區|社群|视频|影片|\bvideo\b/i)
  }
})
