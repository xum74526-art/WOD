import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import {
  localizeInternalBrandText,
  profileUsernameDisplayValue,
  profileUsernameSubmissionValue,
} from '../src/utils/localize-content.ts'
import { displayBusinessReference } from '../src/utils/display-reference.ts'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const supportPage = source('../src/pages/kefu/index.vue')
const profileEditPage = source('../src/pages/profile-edit/index.vue')
const i18n = source('../src/store/i18n.ts')

test('support cards keep the positive service state without negative configuration lines', () => {
  assert.match(supportPage, /supportAiAssisted/)
  assert.match(supportPage, /supportSelfService/)
  assert.doesNotMatch(supportPage, /supportHumanNotConfigured/)
  assert.match(supportPage, /supportTicketPendingNotice/)
  assert.match(i18n, /supportTicketPendingNotice: '工单已保存并进入待分配队列，客服团队将按顺序处理。'/)
  assert.match(i18n, /supportTicketPendingNotice: 'Your ticket has been saved and queued\. The support team will handle it in order\.'/)
  assert.match(supportPage, /displayBusinessReference\(ticket\.ticket_no\)/)
  assert.match(supportPage, /displayBusinessReference\(message\.ticket\.ticket_no\)/)
  assert.equal(displayBusinessReference('WOD-20260910-4E9F8B'), 'KAI星算-20260910-4E9F8B')
})

test('English profile display localizes an untouched Chinese nickname without saving the display value', () => {
  const original = '陈志强'
  const displayed = profileUsernameDisplayValue(original, original, false, 'en')

  assert.equal(displayed, 'Chen Zhiqiang')
  assert.equal(profileUsernameSubmissionValue(original, displayed, false), original)
  assert.match(profileEditPage, /v-model="displayUsername"/)
  assert.match(profileEditPage, /profileUsernameSubmissionValue\(originalUsername\.value, form\.username, usernameEdited\.value\)/)
})

test('an edited nickname is displayed and submitted exactly as entered', () => {
  const original = '陈志强'
  const edited = 'Ethan Chen'

  assert.equal(profileUsernameDisplayValue(original, edited, true, 'en'), edited)
  assert.equal(profileUsernameSubmissionValue(original, edited, true), edited)
  assert.equal(profileUsernameDisplayValue(original, original, false, 'zh-Hans'), original)
})

test('legacy WOD news account is presented with the KAI星算 brand without changing stored data', () => {
  assert.equal(profileUsernameDisplayValue('WOD资讯', 'WOD资讯', false, 'zh-Hans'), 'KAI星算平台行情')
  assert.equal(profileUsernameDisplayValue('WOD资讯', 'WOD资讯', false, 'zh-Hant'), '算力星圖平台行情')
  assert.equal(profileUsernameDisplayValue('WOD资讯', 'WOD资讯', false, 'en'), 'KAI Compute Market')
  assert.equal(profileUsernameSubmissionValue('WOD资讯', 'KAI星算平台行情', false), 'WOD资讯')
})

test('only historical first-party news copy receives the KAI星算 display brand', () => {
  assert.equal(localizeInternalBrandText('WOD 算力行情由 WOD平台发布', 'wod-market'), 'KAI星算 算力行情由 KAI星算平台发布')
  assert.equal(localizeInternalBrandText('ZTW 算力行情', 'wod-market'), 'KAI星算 算力行情')
  assert.equal(localizeInternalBrandText('WOD 算力行情', 'user-post'), 'WOD 算力行情')
  assert.equal(localizeInternalBrandText('兑换码 WOD10', 'wod-market'), '兑换码 WOD10')
})
