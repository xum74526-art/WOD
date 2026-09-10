import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const manifest = JSON.parse(readFileSync(resolve(appRoot, 'src/manifest.json'), 'utf8'))

test('Android package branding presents ZTW while preserving the existing icon assets', () => {
  assert.equal(manifest.name, 'ZTW')
  assert.equal(manifest.description, '算力资源撮合平台 App')
  assert.equal(manifest.h5.title, 'ZTW')
  assert.equal(manifest.versionName, '1.1.9')
  assert.equal(manifest.versionCode, '119')
  assert.equal(manifest.appid, '__UNI__47CF9D3')
  assert.equal(manifest['app-plus'].distribute.android.packagename, 'com.kai.wod')

  const iconPaths = Object.values(manifest['app-plus'].distribute.icons.android) as string[]
  for (const iconPath of iconPaths) {
    assert.match(iconPath, /^src\/static\/logo\//)
    assert.equal(existsSync(resolve(appRoot, iconPath)), true, `${iconPath} must exist`)
  }
})

test('Android login and registration present ZTW with the marketplace description', () => {
  const loginPage = readFileSync(resolve(appRoot, 'src/pages/login/index.vue'), 'utf8')
  const i18n = readFileSync(resolve(appRoot, 'src/store/i18n.ts'), 'utf8')
  assert.match(loginPage, /src="\/static\/logo\/logo\.png"/)
  assert.match(loginPage, /t\('appName'\)/)
  assert.match(loginPage, /t\('算力资源撮合平台'\)/)
  assert.equal([...i18n.matchAll(/appName: 'ZTW'/g)].length, 2)
  assert.doesNotMatch(i18n, /appName: 'KAI'/)
})
