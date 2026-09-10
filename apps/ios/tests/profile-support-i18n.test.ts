import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  localizeInternalBrandText,
  localizePersonName,
  profileUsernameDisplayValue,
  profileUsernameSubmissionValue,
} from '../src/utils/localize-content.ts'

const profileEdit = readFileSync(new URL('../src/pages/profile-edit/index.vue', import.meta.url), 'utf8')
const supportPage = readFileSync(new URL('../src/pages/kefu/index.vue', import.meta.url), 'utf8')
const i18n = readFileSync(new URL('../src/store/i18n.ts', import.meta.url), 'utf8')

test('English profile edit localizes an untouched name without overwriting the stored nickname', () => {
  assert.equal(localizePersonName('陈志强', 'en'), 'Chen Zhiqiang')
  assert.equal(localizePersonName('custom-nickname', 'en'), 'custom-nickname')
  assert.equal(localizePersonName('WOD资讯', 'zh-Hans'), 'ZTW资讯')
  assert.equal(localizePersonName('WOD资讯', 'zh-Hant'), 'ZTW資訊')
  assert.equal(localizePersonName('WOD资讯', 'en'), 'ZTW News')
  assert.equal(profileUsernameDisplayValue('陈志强', '陈志强', false, 'zh-Hant'), '陈志强')
  assert.equal(profileUsernameSubmissionValue('陈志强', 'Chen Zhiqiang', false), '陈志强')
  assert.match(profileEdit, /originalUsername\.value = userStore\.userInfo\?\.username \|\| ''/)
  assert.match(profileEdit, /v-model="displayUsername"/)
  assert.match(profileEdit, /profileUsernameDisplayValue\(originalUsername\.value, form\.username, usernameEdited\.value, i18n\.lang\)/)
  assert.match(profileEdit, /profileUsernameSubmissionValue\(originalUsername\.value, form\.username, usernameEdited\.value\)/)
  assert.match(profileEdit, /updateProfile\(\{ username \}\)/)
  assert.doesNotMatch(profileEdit, /updateProfile\(\{ username: form\.username \}\)/)
})

test('support status copy stays positive and fully localized', () => {
  assert.doesNotMatch(supportPage, /supportHumanNotConfigured|service-note/)
  assert.doesNotMatch(i18n, /supportHumanNotConfigured/)
  assert.match(i18n, /supportTicketPendingNotice: '工单已保存并进入待分配队列，客服团队将按顺序处理。'/)
  assert.match(i18n, /supportTicketPendingNotice: 'Your ticket has been saved and queued\. The support team will handle it in order\.'/)
  assert.doesNotMatch(i18n, /人工坐席和回复时限尚未配置|Human agents and a response SLA are not configured/)
})

test('only historical first-party news copy receives the ZTW display brand', () => {
  assert.equal(localizeInternalBrandText('WOD 算力行情由 WOD平台发布', 'wod-market'), 'ZTW 算力行情由 ZTW平台发布')
  assert.equal(localizeInternalBrandText('WOD 算力行情', 'user-post'), 'WOD 算力行情')
  assert.equal(localizeInternalBrandText('兑换码 WOD10', 'wod-market'), '兑换码 WOD10')
})
