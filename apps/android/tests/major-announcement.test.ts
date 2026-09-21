import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

function read(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

test('major announcement uses the public endpoint and appears before home promotions', () => {
  const api = read('../src/api/notification.ts')
  const home = read('../src/pages/index/index.vue')

  assert.match(api, /'major_announcement' \| 'system'/)
  assert.match(api, /url: '\/notifications\/major-announcement'/)
  assert.match(api, /auth: 'none'/)
  assert.ok(home.indexOf('v-if="majorAnnouncement"') < home.indexOf('<HomePromoCarousel />'))
  assert.match(home, /kai-major-announcement-dismissed:v1:\$\{user\.value\?\.id/)
  assert.match(home, /loadMajorAnnouncement\(\)/)
  assert.match(home, /dismissMajorAnnouncement/)
})

test('notification center exposes the major-announcement category', () => {
  const page = read('../src/pages/notifications/index.vue')
  const i18n = read('../src/store/i18n.ts')

  assert.match(page, /value: 'major_announcement', label: 'majorAnnouncement'/)
  assert.match(page, /major_announcement: 'majorAnnouncement'/)
  assert.match(i18n, /majorAnnouncement: '重大公告'/)
  assert.match(i18n, /majorAnnouncement: 'Major Announcement'/)
})
