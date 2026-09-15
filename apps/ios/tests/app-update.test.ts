import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  compareVersionNames,
  isNewerRelease,
  isTrustedUpdateUrl,
  isValidRelease,
  normalizeVersionCode,
} from '../src/utils/app-update-policy.ts'
import { CLIENT_PLATFORM } from '../src/utils/client-platform.ts'

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const updateUrls = {
  android: 'https://wod.kai.com/download/wod.apk',
  ios: 'https://apps.apple.com/cn/app/ztw/id123456789',
} as const

test('version comparison uses the native numeric code and handles dotted fallbacks', () => {
  assert.equal(normalizeVersionCode('120'), 120)
  assert.equal(normalizeVersionCode('0'), null)
  assert.equal(compareVersionNames('1.2.0', '1.1.10'), 1)
  assert.equal(compareVersionNames('1.1.9', '1.1.9.0'), 0)
  assert.equal(isNewerRelease('1.2.0', 120, {
    platform: CLIENT_PLATFORM,
    available: true,
    latest_version_name: '1.2.1',
    latest_version_code: 121,
    update_url: updateUrls[CLIENT_PLATFORM],
  }), true)
})

test('each platform accepts only its documented HTTPS update channel', () => {
  assert.equal(isTrustedUpdateUrl('android', updateUrls.android), true)
  assert.equal(isTrustedUpdateUrl('ios', updateUrls.ios), true)
  assert.equal(isTrustedUpdateUrl('android', updateUrls.ios), false)
  assert.equal(isTrustedUpdateUrl('ios', updateUrls.android), false)
  assert.equal(isTrustedUpdateUrl('android', 'http://wod.kai.com/download/wod.apk'), false)
  assert.equal(isTrustedUpdateUrl('ios', 'https://evil.example/app'), false)
  assert.equal(isTrustedUpdateUrl(CLIENT_PLATFORM, 123), false)
})

test('release metadata must match the requesting platform', () => {
  const release = {
    platform: CLIENT_PLATFORM,
    available: true,
    latest_version_name: '1.2.0',
    latest_version_code: 120,
    update_url: updateUrls[CLIENT_PLATFORM],
  }
  const otherPlatform = CLIENT_PLATFORM === 'ios' ? 'android' : 'ios'
  assert.equal(isValidRelease(release, CLIENT_PLATFORM), true)
  assert.equal(isValidRelease(release, otherPlatform), false)
  assert.equal(isValidRelease(undefined, CLIENT_PLATFORM), false)
})

test('the app wires automatic and manual update checks through its platform adapter', () => {
  const manifest = JSON.parse(readFileSync(resolve(appRoot, 'src/manifest.json'), 'utf8'))
  const app = readFileSync(resolve(appRoot, 'src/App.vue'), 'utf8')
  const settings = readFileSync(resolve(appRoot, 'src/pages/settings/index.vue'), 'utf8')
  const update = readFileSync(resolve(appRoot, 'src/utils/app-update.ts'), 'utf8')
  const api = readFileSync(resolve(appRoot, 'src/api/platform.ts'), 'utf8')

  assert.equal(manifest.versionName, '1.2.0')
  assert.equal(manifest.versionCode, '120')
  assert.match(update, /APP_FALLBACK_VERSION_NAME = '1\.2\.0'/)
  assert.match(update, /APP_FALLBACK_VERSION_CODE = 120/)
  assert.match(app, /checkForAppUpdate\(CLIENT_PLATFORM\)/)
  assert.match(settings, /checkForAppUpdate\(CLIENT_PLATFORM, \{ manual: true \}\)/)
  assert.match(settings, /appUpdateCheck/)
  assert.match(api, /url: '\/platform\/app-release'/)
  assert.match(api, /auth: 'none'/)
})
