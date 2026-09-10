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

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')

test('version comparison uses the native numeric code and handles dotted fallbacks', () => {
  assert.equal(normalizeVersionCode('119'), 119)
  assert.equal(normalizeVersionCode('0'), null)
  assert.equal(compareVersionNames('1.2.0', '1.1.10'), 1)
  assert.equal(compareVersionNames('1.1.9', '1.1.9.0'), 0)
  assert.equal(isNewerRelease('1.1.9', 119, {
    platform: 'android',
    available: true,
    latest_version_name: '1.1.10',
    latest_version_code: 120,
    update_url: 'https://wod.kai.com/download/wod.apk',
  }), true)
})

test('Android updates only accept the official HTTPS APK location', () => {
  assert.equal(isTrustedUpdateUrl('android', 'https://wod.kai.com/download/wod.apk'), true)
  assert.equal(isTrustedUpdateUrl('android', 'http://wod.kai.com/download/wod.apk'), false)
  assert.equal(isTrustedUpdateUrl('android', 'https://evil.example/wod.apk'), false)
  assert.equal(isTrustedUpdateUrl('android', 'https://wod.kai.com/download/wod.apk?next=evil'), false)
  assert.equal(isTrustedUpdateUrl('android', 123), false)
})

test('release metadata must match the requesting platform', () => {
  const release = {
    platform: 'android' as const,
    available: true,
    latest_version_name: '1.1.9',
    latest_version_code: 119,
    update_url: 'https://wod.kai.com/download/wod.apk',
  }
  assert.equal(isValidRelease(release, 'android'), true)
  assert.equal(isValidRelease(release, 'ios'), false)
  assert.equal(isValidRelease(undefined, 'android'), false)
})

test('Android app wires automatic and manual update checks without changing release version', () => {
  const manifest = JSON.parse(readFileSync(resolve(appRoot, 'src/manifest.json'), 'utf8'))
  const app = readFileSync(resolve(appRoot, 'src/App.vue'), 'utf8')
  const settings = readFileSync(resolve(appRoot, 'src/pages/settings/index.vue'), 'utf8')
  const update = readFileSync(resolve(appRoot, 'src/utils/app-update.ts'), 'utf8')
  const api = readFileSync(resolve(appRoot, 'src/api/platform.ts'), 'utf8')

  assert.equal(manifest.versionName, '1.1.9')
  assert.equal(manifest.versionCode, '119')
  assert.match(update, /APP_FALLBACK_VERSION_NAME = '1\.1\.9'/)
  assert.match(update, /APP_FALLBACK_VERSION_CODE = 119/)
  assert.match(app, /checkForAppUpdate\('android'\)/)
  assert.match(settings, /checkForAppUpdate\('android', \{ manual: true \}\)/)
  assert.match(settings, /appUpdateCheck/)
  assert.match(api, /url: '\/platform\/app-release'/)
  assert.match(api, /auth: 'none'/)
})
