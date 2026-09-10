import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  DEFAULT_LANGUAGE,
  languageDocumentTag,
  languageLocale,
  nextLanguage,
  normalizeStoredLanguage,
  supportApiLanguage,
} from '../src/utils/language.ts'
import { toTraditionalChinese } from '../src/utils/traditional-chinese.ts'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

test('Traditional Chinese is the iOS default and legacy preferences migrate safely', () => {
  assert.equal(DEFAULT_LANGUAGE, 'zh-Hant')
  assert.equal(normalizeStoredLanguage(undefined), 'zh-Hant')
  assert.equal(normalizeStoredLanguage('zh'), 'zh-Hant')
  assert.equal(normalizeStoredLanguage('zh-TW'), 'zh-Hant')
  assert.equal(normalizeStoredLanguage('zh-CN'), 'zh-Hans')
  assert.equal(normalizeStoredLanguage('en'), 'en')
})

test('iOS language metadata and switching cover all three languages', () => {
  assert.equal(languageLocale('zh-Hant'), 'zh-TW')
  assert.equal(languageLocale('zh-Hans'), 'zh-CN')
  assert.equal(languageLocale('en'), 'en-US')
  assert.equal(languageDocumentTag('zh-Hant'), 'zh-Hant')
  assert.equal(nextLanguage('zh-Hant'), 'zh-Hans')
  assert.equal(nextLanguage('zh-Hans'), 'en')
  assert.equal(nextLanguage('en'), 'zh-Hant')
  assert.equal(supportApiLanguage('zh-Hant'), 'zh')
})

test('the iOS converter covers fixed and runtime business terminology', () => {
  assert.equal(
    toTraditionalChinese('设置、视频上传、账号注销、资产、卡时、联系我们'),
    '設置、視頻上傳、賬號註銷、資產、卡時、聯繫我們',
  )
})

test('iOS entry points apply Traditional Chinese throughout the app', () => {
  const i18n = source('../src/store/i18n.ts')
  const languageToggle = source('../src/components/LanguageToggle.vue')
  const settings = source('../src/pages/settings/index.vue')
  const agreement = source('../src/pages/agreement/index.vue')
  const support = source('../src/pages/kefu/index.vue')
  const rechargeOrders = source('../src/pages/wallet/recharges.vue')
  const forgotPassword = source('../src/pages/forgot-password/index.vue')
  const resetPassword = source('../src/pages/reset-password/index.vue')
  const productDetail = source('../src/pages/product/detail.vue')
  const communityDetail = source('../src/pages/community/detail.vue')
  const generated = source('../src/store/i18n_generated.ts')
  const request = source('../src/api/request.ts')
  const htmlEntry = source('../index.html')
  const manifest = JSON.parse(source('../src/manifest.json')) as { locale?: string }
  const nativeLocale = JSON.parse(source('../src/locale/zh-Hant.json')) as Record<string, string>
  const uniLocale = JSON.parse(source('../src/locale/uni-app.zh-Hant.json')) as {
    common?: Record<string, string>
  }

  assert.equal(manifest.locale, 'zh-Hant')
  assert.match(htmlEntry, /<html lang="zh-Hant">/)
  assert.match(htmlEntry, /<title>ZTW<\/title>/)
  assert.equal(nativeLocale['app.name'], 'ZTW')
  assert.equal(nativeLocale['tab.home'], '首頁')
  assert.equal(nativeLocale['tab.community'], '資訊')
  assert.equal(uniLocale.common?.['uni.showModal.confirm'], '確定')
  assert.equal(uniLocale.common?.['uni.chooseImage.sourceType.album'], '從相簿選擇')
  assert.match(i18n, /normalizeStoredLanguage\(saved\)/)
  assert.match(i18n, /toTraditionalChinese\(value\)/)
  assert.match(languageToggle, /uni\.showActionSheet/)
  assert.match(languageToggle, /language: 'zh-Hant', label: '繁體中文'/)
  assert.match(languageToggle, /language: 'zh-Hans', label: '简体中文'/)
  assert.match(languageToggle, /language: 'en', label: 'English'/)
  assert.doesNotMatch(languageToggle, /i18n\.toggle\(\)/)
  assert.match(settings, /language: 'zh-Hant'/)
  assert.match(settings, /language: 'zh-Hans'/)
  assert.match(settings, /language: 'en'/)
  assert.match(settings, /t\('versionLabel'\)/)
  assert.doesNotMatch(settings, /i18n\.lang === 'en' \? 'Version' : '版本'/)
  assert.match(rechargeOrders, /:aria-label="t\('loading'\)"/)
  assert.match(forgotPassword, /t\('passwordRecoveryKicker'\)/)
  assert.match(resetPassword, /t\('passwordResetKicker'\)/)
  assert.match(productDetail, /toLocaleString\(i18n\.locale\)/)
  assert.match(communityDetail, /:title="t\('videoPlayer'\)"/)
  assert.match(generated, /Password: xxxx/)
  assert.match(generated, /ID document images are used only for verification and are not displayed publicly\./)
  assert.match(agreement, /paragraphs: section\.paragraphs\.map\(toTraditionalChinese\)/)
  assert.match(support, /supportApiLanguage\(i18n\.lang\)/)
  assert.equal((request.match(/'Accept-Language': i18n\.locale/g) || []).length, 2)
})
