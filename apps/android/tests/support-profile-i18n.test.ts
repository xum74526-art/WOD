import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import {
  localizeInternalBrandText,
  profileUsernameDisplayValue,
  profileUsernameSubmissionValue,
} from '../src/utils/localize-content.ts'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const supportPage = source('../src/pages/kefu/index.vue')
const profileEditPage = source('../src/pages/profile-edit/index.vue')

test('support cards keep the positive service state without negative configuration lines', () => {
  assert.match(supportPage, /supportAiAssisted/)
  assert.match(supportPage, /supportSelfService/)
  assert.doesNotMatch(supportPage, /supportHumanNotConfigured/)
  assert.doesNotMatch(supportPage, /supportTicketPendingNotice/)
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
  assert.equal(profileUsernameDisplayValue(original, original, false, 'zh'), original)
})

test('legacy WOD news account is presented with the ZTW brand without changing stored data', () => {
  assert.equal(profileUsernameDisplayValue('WOD资讯', 'WOD资讯', false, 'zh'), 'ZTW资讯')
  assert.equal(profileUsernameDisplayValue('WOD资讯', 'WOD资讯', false, 'en'), 'ZTW News')
  assert.equal(profileUsernameSubmissionValue('WOD资讯', 'ZTW资讯', false), 'WOD资讯')
})

test('only historical first-party news copy receives the ZTW display brand', () => {
  assert.equal(localizeInternalBrandText('WOD 算力行情由 WOD平台发布', 'wod-market'), 'ZTW 算力行情由 ZTW平台发布')
  assert.equal(localizeInternalBrandText('WOD 算力行情', 'user-post'), 'WOD 算力行情')
  assert.equal(localizeInternalBrandText('兑换码 WOD10', 'wod-market'), '兑换码 WOD10')
})
