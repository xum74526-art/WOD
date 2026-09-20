import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const manifest = readFileSync(
  new URL('../nativeResources/ios/PrivacyInfo.xcprivacy', import.meta.url),
  'utf8',
)

test('iOS ships an app privacy manifest with tracking disabled', () => {
  assert.match(manifest, /^<\?xml version="1\.0" encoding="UTF-8"\?>/)
  assert.ok(manifest.trimEnd().endsWith('</plist>'))
  assert.doesNotMatch(manifest, /^(?:\+|EOF$|plutil\b)/m)
  assert.match(manifest, /<key>NSPrivacyTracking<\/key>\s*<false\/>/)
  assert.match(manifest, /<key>NSPrivacyTrackingDomains<\/key>\s*<array\/>/)
  assert.doesNotMatch(manifest, /NSPrivacyCollectedDataTypePurpose(?:ThirdParty|Developer)Advertising/)
})

test('iOS declares the data categories collected by first-party app features', () => {
  for (const category of [
    'Name',
    'EmailAddress',
    'PhoneNumber',
    'PhysicalAddress',
    'PaymentInfo',
    'OtherFinancialInfo',
    'SensitiveInfo',
    'PhotosorVideos',
    'CustomerSupport',
    'OtherUserContent',
    'UserID',
    'PurchaseHistory',
    'ProductInteraction',
    'CrashData',
    'OtherDiagnosticData',
  ]) {
    assert.match(manifest, new RegExp(`<string>NSPrivacyCollectedDataType${category}</string>`))
  }
  assert.match(manifest, /NSPrivacyCollectedDataTypePurposeAppFunctionality/)
  assert.doesNotMatch(manifest, /NSPrivacyCollectedDataTypeAudioData/)
})

test('iOS declares the required-reason APIs used by the packaged DCloud runtime', () => {
  const expected = new Map([
    ['NSPrivacyAccessedAPICategoryUserDefaults', ['CA92.1']],
    ['NSPrivacyAccessedAPICategoryFileTimestamp', ['C617.1']],
    ['NSPrivacyAccessedAPICategoryDiskSpace', ['E174.1', '7D9E.1']],
    ['NSPrivacyAccessedAPICategorySystemBootTime', ['35F9.1']],
  ])

  for (const [category, reasons] of expected) {
    assert.match(manifest, new RegExp(`<string>${category}</string>`))
    for (const reason of reasons) assert.ok(manifest.includes(`<string>${reason}</string>`))
  }
})
