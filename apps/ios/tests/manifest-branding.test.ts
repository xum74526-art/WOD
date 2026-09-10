import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const manifest = JSON.parse(readFileSync(resolve(appRoot, 'src/manifest.json'), 'utf8'))

test('iOS package identity and icon paths use the ZTW Vue 3 source tree', () => {
  assert.equal(manifest.name, 'ZTW')
  assert.equal(manifest.description, '算力资源撮合平台 App')
  assert.equal(manifest.h5.title, 'ZTW')
  assert.equal(manifest.versionName, '1.1.9')
  assert.equal(manifest.versionCode, '119')
  assert.equal(manifest.vueVersion, '3')
  assert.equal(manifest.appid, '__UNI__47CF9D3')
  assert.equal(manifest['app-plus'].distribute.ios.appid, 'com.kai.wod')

  const icons = manifest['app-plus'].distribute.icons.ios
  const paths = [
    icons.appstore,
    icons.ipad.app,
    icons.ipad['app@2x'],
    icons.iphone['app@2x'],
    icons.iphone['app@3x'],
  ]
  for (const iconPath of paths) {
    assert.match(iconPath, /^src\/static\/logo\//)
    assert.equal(existsSync(resolve(appRoot, iconPath)), true, `${iconPath} must exist`)
  }
  assert.equal(existsSync(resolve(appRoot, 'assets/branding/app-icon-master.png')), true)
})

test('iOS App Store icon stays unchanged while login and registration present ZTW', () => {
  const icon = readFileSync(resolve(appRoot, manifest['app-plus'].distribute.icons.ios.appstore))
  assert.equal(icon.subarray(1, 4).toString('ascii'), 'PNG')
  assert.equal(icon.readUInt32BE(16), 1024)
  assert.equal(icon.readUInt32BE(20), 1024)

  const loginPage = readFileSync(resolve(appRoot, 'src/pages/login/index.vue'), 'utf8')
  const i18n = readFileSync(resolve(appRoot, 'src/store/i18n.ts'), 'utf8')
  assert.match(loginPage, /src="\/static\/logo\/logo\.png"/)
  assert.match(loginPage, /t\('appName'\)/)
  assert.match(loginPage, /t\('算力资源撮合平台'\)/)
  assert.equal([...i18n.matchAll(/appName: 'ZTW'/g)].length, 2)
  assert.doesNotMatch(i18n, /appName: 'KAI'/)
})
