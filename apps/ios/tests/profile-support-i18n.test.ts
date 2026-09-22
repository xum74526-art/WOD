import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  localizeInternalBrandText,
  localizePersonName,
  profileUsernameDisplayValue,
  profileUsernameSubmissionValue,
} from '../src/utils/localize-content.ts'
import { displayBusinessReference } from '../src/utils/display-reference.ts'

const profileEdit = readFileSync(new URL('../src/pages/profile-edit/index.vue', import.meta.url), 'utf8')
const supportPage = readFileSync(new URL('../src/pages/kefu/index.vue', import.meta.url), 'utf8')
const i18n = readFileSync(new URL('../src/store/i18n.ts', import.meta.url), 'utf8')

test('English profile edit localizes an untouched name without overwriting the stored nickname', () => {
  assert.equal(localizePersonName('陈志强', 'en'), 'Chen Zhiqiang')
  assert.equal(localizePersonName('custom-nickname', 'en'), 'custom-nickname')
  assert.equal(localizePersonName('WOD资讯', 'zh-Hans'), 'KAI星算平台行情')
  assert.equal(localizePersonName('WOD资讯', 'zh-Hant'), '算力星圖平台行情')
  assert.equal(localizePersonName('WOD资讯', 'en'), 'KAI Compute Market')
  assert.equal(localizePersonName('ZTW资讯', 'zh-Hans'), 'KAI星算平台行情')
  assert.equal(localizePersonName('ZTW资讯', 'zh-Hant'), '算力星圖平台行情')
  assert.equal(localizePersonName('ZTW资讯', 'en'), 'KAI Compute Market')
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
  assert.match(supportPage, /displayBusinessReference\(ticket\.ticket_no\)/)
  assert.match(supportPage, /displayBusinessReference\(message\.ticket\.ticket_no\)/)
  assert.equal(displayBusinessReference('WOD-20260910-4E9F8B'), 'KAI星算-20260910-4E9F8B')
})

test('shared inquiry-mode labels stay aligned with Android wording', () => {
  assert.match(i18n, /buyCompute: '算力市场'/)
  assert.match(i18n, /buyCompute: 'Compute Market'/)
  assert.match(i18n, /buyRequests: '需求'/)
  assert.match(i18n, /buyRequests: 'Requests'/)
  assert.match(i18n, /inquiryQuantityHint: '填写预计数量，实际可用量将在需求沟通时确认。'/)
  assert.match(i18n, /inquiryQuantityHint: 'Enter the expected quantity\. Availability will be confirmed during follow-up\.'/)
  assert.match(i18n, /recoveryEmailUnavailable: '邮箱服务暂不可用，目前不能绑定或更换邮箱。'/)
  assert.match(i18n, /recoveryEmailUnavailable: 'Email service is unavailable, so an email cannot be bound or changed right now\.'/)
})

test('only historical first-party news copy receives the KAI星算 display brand', () => {
  assert.equal(localizeInternalBrandText('WOD 算力行情由 WOD平台发布', 'wod-market'), 'KAI星算 算力行情由 KAI星算平台发布')
  assert.equal(localizeInternalBrandText('ZTW 算力行情', 'wod-market'), 'KAI星算 算力行情')
  assert.equal(localizeInternalBrandText('WOD 算力行情', 'user-post'), 'WOD 算力行情')
  assert.equal(localizeInternalBrandText('兑换码 WOD10', 'wod-market'), '兑换码 WOD10')
})
