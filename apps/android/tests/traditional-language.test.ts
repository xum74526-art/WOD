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

test('Traditional Chinese is the default and legacy Chinese preferences migrate safely', () => {
  assert.equal(DEFAULT_LANGUAGE, 'zh-Hant')
  assert.equal(normalizeStoredLanguage(undefined), 'zh-Hant')
  assert.equal(normalizeStoredLanguage('zh'), 'zh-Hant')
  assert.equal(normalizeStoredLanguage('zh-TW'), 'zh-Hant')
  assert.equal(normalizeStoredLanguage('zh-CN'), 'zh-Hans')
  assert.equal(normalizeStoredLanguage('en'), 'en')
})

test('language metadata and switch order cover all three app languages', () => {
  assert.equal(languageLocale('zh-Hant'), 'zh-TW')
  assert.equal(languageLocale('zh-Hans'), 'zh-CN')
  assert.equal(languageLocale('en'), 'en-US')
  assert.equal(languageDocumentTag('zh-Hant'), 'zh-Hant')
  assert.equal(nextLanguage('zh-Hant'), 'zh-Hans')
  assert.equal(nextLanguage('zh-Hans'), 'en')
  assert.equal(nextLanguage('en'), 'zh-Hant')
  assert.equal(supportApiLanguage('zh-Hant'), 'zh')
})

test('the converter covers fixed and runtime business terminology', () => {
  assert.equal(
    toTraditionalChinese('设置、视频上传、账号注销、资产、卡时、联系我们'),
    '設置、視頻上傳、賬號註銷、資產、卡時、聯繫我們',
  )
})

test('Android entry points apply Traditional Chinese beyond the home page', () => {
  const i18n = source('../src/store/i18n.ts')
  const settings = source('../src/pages/settings/index.vue')
  const agreement = source('../src/pages/agreement/index.vue')
  const support = source('../src/pages/kefu/index.vue')
  const request = source('../src/api/request.ts')

  assert.match(i18n, /normalizeStoredLanguage\(saved\)/)
  assert.match(i18n, /toTraditionalChinese\(value\)/)
  assert.match(settings, /language: 'zh-Hant'/)
  assert.match(settings, /language: 'zh-Hans'/)
  assert.match(settings, /language: 'en'/)
  assert.match(agreement, /paragraphs: section\.paragraphs\.map\(toTraditionalChinese\)/)
  assert.match(support, /supportApiLanguage\(i18n\.lang\)/)
  assert.equal((request.match(/'Accept-Language': i18n\.locale/g) || []).length, 2)
})
