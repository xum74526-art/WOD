import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { CLIENT_PLATFORM } from '../src/utils/client-platform.ts'

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const manifest = JSON.parse(readFileSync(resolve(appRoot, 'src/manifest.json'), 'utf8'))

function stringLeaves(value: unknown): string[] {
  if (typeof value === 'string') return [value]
  if (!value || typeof value !== 'object') return []
  return Object.values(value).flatMap(stringLeaves)
}

test('native package identity and icon paths use the ZTW Vue 3 source tree', () => {
  assert.equal(manifest.name, 'ZTW')
  assert.equal(manifest.description, '算力资源撮合平台 App')
  assert.equal(manifest.h5.title, 'ZTW')
  assert.equal(manifest.versionName, '1.2.0')
  assert.equal(manifest.versionCode, '120')
  assert.equal(manifest.vueVersion, '3')
  assert.equal(manifest.appid, '__UNI__47CF9D3')

  const platformConfig = manifest['app-plus'].distribute[CLIENT_PLATFORM]
  const packageId = CLIENT_PLATFORM === 'ios' ? platformConfig.appid : platformConfig.packagename
  assert.equal(packageId, 'com.kai.wod')

  const iconPaths = stringLeaves(manifest['app-plus'].distribute.icons[CLIENT_PLATFORM])
  assert.ok(iconPaths.length >= 4)
  for (const iconPath of iconPaths) {
    assert.match(iconPath, /^src\/static\/logo\//)
    assert.equal(existsSync(resolve(appRoot, iconPath)), true, `${iconPath} must exist`)
  }
  assert.equal(existsSync(resolve(appRoot, 'assets/branding/app-icon-master.png')), true)
})

test('login, registration and the native icon present the ZTW brand', () => {
  if (CLIENT_PLATFORM === 'ios') {
    const iconPath = manifest['app-plus'].distribute.icons.ios.appstore
    const icon = readFileSync(resolve(appRoot, iconPath))
    assert.equal(icon.subarray(1, 4).toString('ascii'), 'PNG')
    assert.equal(icon.readUInt32BE(16), 1024)
    assert.equal(icon.readUInt32BE(20), 1024)
  }

  const loginPage = readFileSync(resolve(appRoot, 'src/pages/login/index.vue'), 'utf8')
  const i18n = readFileSync(resolve(appRoot, 'src/store/i18n.ts'), 'utf8')
  assert.match(loginPage, /src="\/static\/logo\/logo\.png"/)
  assert.match(loginPage, /t\('appName'\)/)
  assert.match(loginPage, /t\('算力资源撮合平台'\)/)
  assert.equal([...i18n.matchAll(/appName: 'ZTW'/g)].length, 2)
  assert.doesNotMatch(i18n, /appName: 'KAI'/)
})
