import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  DEFAULT_LANGUAGE,
  LANGUAGE_OPTIONS,
  languageDocumentTag,
  languageLocale,
  languageOption,
  nextLanguage,
  normalizeStoredLanguage,
  supportApiLanguage,
} from '../src/utils/language.ts'
import { toTraditionalChinese } from '../src/utils/traditional-chinese.ts'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

test('Traditional Chinese is the mobile default and legacy preferences migrate safely', () => {
  assert.equal(DEFAULT_LANGUAGE, 'zh-Hant')
  assert.equal(normalizeStoredLanguage(undefined), 'zh-Hant')
  assert.equal(normalizeStoredLanguage('zh'), 'zh-Hant')
  assert.equal(normalizeStoredLanguage('zh-TW'), 'zh-Hant')
  assert.equal(normalizeStoredLanguage('zh-CN'), 'zh-Hans')
  assert.equal(normalizeStoredLanguage('en'), 'en')
})

test('mobile language metadata and switching cover all three languages', () => {
  assert.deepEqual(LANGUAGE_OPTIONS, [
    { language: 'zh-Hant', label: '繁體中文', shortLabel: '繁中', locale: 'zh-TW', mark: '繁' },
    { language: 'zh-Hans', label: '简体中文', shortLabel: '简中', locale: 'zh-CN', mark: '简' },
    { language: 'en', label: 'English', shortLabel: 'EN', locale: 'en-US', mark: 'EN' },
  ])
  assert.equal(languageOption('zh-Hant').shortLabel, '繁中')
  assert.equal(languageLocale('zh-Hant'), 'zh-TW')
  assert.equal(languageLocale('zh-Hans'), 'zh-CN')
  assert.equal(languageLocale('en'), 'en-US')
  assert.equal(languageDocumentTag('zh-Hant'), 'zh-Hant')
  assert.equal(nextLanguage('zh-Hant'), 'zh-Hans')
  assert.equal(nextLanguage('zh-Hans'), 'en')
  assert.equal(nextLanguage('en'), 'zh-Hant')
  assert.equal(supportApiLanguage('zh-Hant'), 'zh')
})

test('the mobile converter covers fixed and runtime business terminology', () => {
  assert.equal(
    toTraditionalChinese('设置、视频上传、账号注销、资产、卡时、联系我们'),
    '設置、視頻上傳、賬號註銷、資產、卡時、聯繫我們',
  )
  assert.equal(
    toTraditionalChinese('欢迎使用KAI星算移动客户端'),
    '歡迎使用KAI星算移動客戶端',
  )
})

test('mobile entry points apply Traditional Chinese throughout the app', () => {
  const i18n = source('../src/store/i18n.ts')
  const languageToggle = source('../src/components/LanguageToggle.vue')
  const languageSelector = source('../src/components/LanguageSelectorSheet.vue')
  const settings = source('../src/pages/settings/index.vue')
  const agreement = source('../src/pages/agreement/index.vue')
  const legalDocuments = source('../src/config/legal-documents.ts')
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
  assert.match(htmlEntry, /<title>KAI星算<\/title>/)
  assert.equal(nativeLocale['app.name'], 'KAI星算')
  assert.equal(nativeLocale['tab.home'], '首頁')
  assert.equal(nativeLocale['tab.community'], '社群')
  assert.equal(uniLocale.common?.['uni.showModal.confirm'], '確定')
  assert.equal(uniLocale.common?.['uni.chooseImage.sourceType.album'], '從相簿選擇')
  assert.match(i18n, /normalizeStoredLanguage\(saved\)/)
  assert.match(i18n, /toTraditionalChinese\(value\)/)
  assert.match(languageToggle, /<LanguageSelectorSheet/)
  assert.match(languageToggle, /aria-haspopup="dialog"/)
  assert.match(languageToggle, /languageOption\(i18n\.lang\)/)
  assert.doesNotMatch(languageToggle, /uni\.showActionSheet/)
  assert.doesNotMatch(languageToggle, /i18n\.toggle\(\)/)
  assert.match(languageSelector, /role="dialog"/)
  assert.match(languageSelector, /role="radiogroup"/)
  assert.match(languageSelector, /role="radio"/)
  assert.match(languageSelector, /LANGUAGE_OPTIONS/)
  assert.match(languageSelector, /aria-checked/)
  assert.match(languageSelector, /i18n\.setLanguage\(language\)/)
  assert.match(languageSelector, /uni\.hideTabBar/)
  assert.match(languageSelector, /uni\.showTabBar/)
  assert.match(languageSelector, /prefers-reduced-motion: reduce/)
  assert.match(languageSelector, /event\.key === 'Escape'/)
  assert.match(languageSelector, /restoreFocus\(\)/)
  assert.match(settings, /<LanguageSelectorSheet v-model:visible="showLanguageSelector"/)
  assert.match(settings, /languageOption\(i18n\.lang\)\.label/)
  assert.match(settings, /showLanguageSelector\.value = true/)
  assert.equal((settings.match(/uni\.showActionSheet/g) || []).length, 1)
  assert.match(settings, /t\('versionLabel'\)/)
  assert.doesNotMatch(settings, /i18n\.lang === 'en' \? 'Version' : '版本'/)
  assert.match(rechargeOrders, /:aria-label="t\('loading'\)"/)
  assert.match(forgotPassword, /t\('passwordRecoveryKicker'\)/)
  assert.match(resetPassword, /t\('passwordResetKicker'\)/)
  assert.match(productDetail, /toLocaleString\(i18n\.locale\)/)
  assert.match(communityDetail, /:title="t\('videoPlayer'\)"/)
  assert.match(generated, /Password: xxxx/)
  assert.match(generated, /ID document images are used only for verification and are not displayed publicly\./)
  assert.match(agreement, /getLegalDocument\(kind\.value, i18n\.lang\)/)
  assert.match(legalDocuments, /paragraphs: section\.paragraphs\.map\(toTraditionalLegalText\)/)
  assert.match(legalDocuments, /language === 'zh-Hant' \? toTraditional\(source\) : source/)
  assert.match(support, /supportApiLanguage\(i18n\.lang\)/)
  assert.equal((request.match(/'Accept-Language': i18n\.locale/g) || []).length, 2)
})
