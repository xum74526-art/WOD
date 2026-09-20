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

test('native package identity and icon paths use the KAI星算 Vue 3 source tree', () => {
  assert.equal(manifest.name, 'KAI星算')
  assert.equal(manifest.description, '算力资源撮合平台 App')
  assert.equal(manifest.h5.title, 'KAI星算')
  assert.equal(manifest.versionName, '1.2.1')
  assert.equal(manifest.versionCode, '124')
  assert.equal(manifest.vueVersion, '3')
  assert.equal(manifest.appid, '__UNI__47CF9D3')

  const platformConfig = manifest['app-plus'].distribute[CLIENT_PLATFORM]
  const packageId = CLIENT_PLATFORM === 'ios' ? platformConfig.appid : platformConfig.packagename
  assert.equal(packageId, 'com.kai.ztwstarmap')
  assert.equal(manifest['app-plus'].distribute.ios.urltypes, 'kai')

  const iconPaths = stringLeaves(manifest['app-plus'].distribute.icons[CLIENT_PLATFORM])
  assert.ok(iconPaths.length >= 3)
  for (const iconPath of iconPaths) {
    assert.match(iconPath, /^src\/static\/logo\//)
    assert.equal(existsSync(resolve(appRoot, iconPath)), true, `${iconPath} must exist`)
  }
  assert.equal(existsSync(resolve(appRoot, 'assets/branding/app-icon-master.png')), true)
})

test('native transport refuses untrusted TLS certificates', () => {
  assert.deepEqual(manifest['app-plus'].ssl, { untrustedca: 'refuse' })
})

test('login, registration and the native icon present the KAI星算 brand', () => {
  if (CLIENT_PLATFORM === 'ios') {
    const iosIcons = manifest['app-plus'].distribute.icons.ios
    for (const [iconPath, size] of [
      [iosIcons.appstore, 1024],
      [iosIcons.iphone['app@2x'], 120],
      [iosIcons.iphone['app@3x'], 180],
    ] as Array<[string, number]>) {
      const icon = readFileSync(resolve(appRoot, iconPath))
      assert.equal(icon.subarray(1, 4).toString('ascii'), 'PNG')
      assert.equal(icon.readUInt32BE(16), size)
      assert.equal(icon.readUInt32BE(20), size)
      assert.equal(icon.readUInt8(25), 2, `${iconPath} must use RGB without alpha`)
    }
  }

  const loginPage = readFileSync(resolve(appRoot, 'src/pages/login/index.vue'), 'utf8')
  const i18n = readFileSync(resolve(appRoot, 'src/store/i18n.ts'), 'utf8')
  assert.match(loginPage, /src="\/static\/logo\/logo\.png"/)
  assert.match(loginPage, /t\('appName'\)/)
  assert.match(loginPage, /t\('算力资源撮合平台'\)/)
  assert.equal([...i18n.matchAll(/appName: 'KAI星算'/g)].length, 2)
  assert.doesNotMatch(i18n, /appName: 'KAI'/)
})
