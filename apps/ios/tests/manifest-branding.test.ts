import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { CLIENT_PLATFORM } from '../src/utils/client-platform.ts'
import { isPaymentAppUrl } from '../src/utils/payment-checkout.ts'

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
  assert.equal(manifest.versionName, '1.2.4')
  assert.equal(manifest.versionCode, '130')
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

test('iOS permits querying every wallet scheme that checkout hands to the native runtime', () => {
  const configured = manifest['app-plus'].distribute.ios.urlschemewhitelist
  const schemes = typeof configured === 'string' ? configured.split(',') : (configured || [])
  // Build 129 omitted Alipay. Its native runtime calls canOpenURL before openURL,
  // which fails for undeclared schemes even when the wallet app is installed.
  for (const url of ['alipays://platformapi/startapp', 'alipay://platformapi/startapp', 'weixin://wap/pay']) {
    assert.equal(isPaymentAppUrl(url), true)
    assert.ok(schemes.includes(url.split(':')[0]), `iOS query whitelist must cover ${url.split(':')[0]}`)
  }
  assert.ok(schemes.length <= 50)
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
  assert.equal([...i18n.matchAll(/appName: 'KAI星算'/g)].length, 1)
  assert.equal([...i18n.matchAll(/appName: 'KAI Star'/g)].length, 1)
  assert.doesNotMatch(i18n, /appName: 'KAI'/)

  const englishLocale = JSON.parse(readFileSync(resolve(appRoot, 'src/locale/en.json'), 'utf8'))
  assert.equal(englishLocale['app.name'], 'KAI Star')

  const privacyConsent = readFileSync(resolve(appRoot, 'src/pages/privacy-consent/index.vue'), 'utf8')
  const settingsPage = readFileSync(resolve(appRoot, 'src/pages/settings/index.vue'), 'utf8')
  const legalDocuments = readFileSync(resolve(appRoot, 'src/config/legal-documents.ts'), 'utf8')
  assert.match(privacyConsent, /en:\s*\{\s*appName: 'KAI Star'/)
  assert.match(settingsPage, /content: `\$\{t\('appName'\)\}/)
  assert.doesNotMatch(legalDocuments.slice(legalDocuments.indexOf('const PRIVACY_EN'), legalDocuments.indexOf('function agreementZh')), /KAI星算/)
  assert.doesNotMatch(legalDocuments.slice(legalDocuments.indexOf('function agreementEn'), legalDocuments.indexOf('const PROTECTED_LEGAL_VALUES')), /KAI星算/)
})

test('native home-screen names follow the selected system language', () => {
  const localizedNames = [
    ['en', 'KAI Star'],
    ['zh-Hans', 'KAI星算'],
    ['zh-Hant', 'KAI星算'],
  ] as const

  for (const [locale, expectedName] of localizedNames) {
    const infoPlistStrings = readFileSync(
      resolve(appRoot, `nativeResources/ios/Resources/${locale}.lproj/InfoPlist.strings`),
      'utf8',
    )
    assert.match(infoPlistStrings, new RegExp(`"CFBundleDisplayName"\\s*=\\s*"${expectedName}";`))
    assert.match(infoPlistStrings, new RegExp(`"CFBundleName"\\s*=\\s*"${expectedName}";`))
  }
})
